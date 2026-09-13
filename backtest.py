"""Causal, long-only spot research engine. Decimal accounting; no broker orders."""
import argparse
import csv
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
import hashlib
import json
import math
from pathlib import Path
import statistics

D = lambda x: Decimal(str(x))
ROOT = Path(__file__).resolve().parent

@dataclass(frozen=True)
class Params:
    capital: float = 1000
    notional: float = 100
    fee_bps: float = 10
    slippage_bps: float = 2
    spread_bps: float = 2
    fast: int = 5
    slow: int = 20
    gap_bps: float = 0
    max_drawdown: float = .05
    daily_loss: float = .02
    max_entries_day: int = 12
    cooldown_bars: int = 3
    qty_step: str = '0.000001'
    min_notional: float = 5
    hourly_overhead: float = 0

    def validate(self):
        for k,v in asdict(self).items():
            if k != 'qty_step' and (not math.isfinite(v) or v < 0):
                raise ValueError('Invalid parameter: '+k)
        if not (0 < self.capital and 0 < self.notional <= self.capital):
            raise ValueError('Invalid capital/notional')
        if not 0 < self.max_drawdown < 1 or not 0 < self.daily_loss < 1:
            raise ValueError('Invalid limits')
        if not 1 <= self.fast < self.slow:
            raise ValueError('Invalid windows')
        for k in ('fast','slow','max_entries_day','cooldown_bars'):
            if type(getattr(self,k)) is not int:
                raise ValueError('Integer required: '+k)
        if max(self.fee_bps,self.slippage_bps,self.spread_bps) >= 1000:
            raise ValueError('Costs out of range')
        if not D(self.qty_step).is_finite() or D(self.qty_step) <= 0:
            raise ValueError('Invalid step')
        return self


def read_candles(path):
    with open(path) as f:
        rows = [{k: (int(v) if k=='timestamp' else float(v)) for k,v in row.items()}
                for row in csv.DictReader(f)]
    validate_candles(rows)
    return rows


def validate_candles(rows):
    if not rows:
        raise ValueError('No candles')
    last = None
    for r in rows:
        ts = r['timestamp']
        if type(ts) is not int or ts % 300 or (last is not None and ts-last != 300):
            raise ValueError('Duplicate, out-of-order, or gapped 5m candles')
        vals = [r[k] for k in ('open','high','low','close','volume')]
        if not all(math.isfinite(x) for x in vals) or min(vals[:4])<=0 or vals[4]<0:
            raise ValueError('Invalid OHLCV')
        if r['low']>min(r['open'],r['close']) or r['high']<max(r['open'],r['close']):
            raise ValueError('Inconsistent OHLC')
        last=ts


def signal(history, p, strategy):
    if strategy == 'cash': return False
    if strategy == 'hold': return True
    if strategy != 'sma': raise ValueError('Unknown strategy')
    if len(history)<p.slow: return False
    fast = statistics.mean(history[-p.fast:])
    slow = statistics.mean(history[-p.slow:])
    return fast/slow-1 > p.gap_bps/10000


def simulate(rows, p=Params(), strategy='sma', warmup=()):
    p.validate(); validate_candles(rows)
    cash, qty = D(p.capital), D(0)
    entry_cost, entry_fee, entry_price = D(0), D(0), D(0)
    fees = D(0)
    trades, curve = [], []
    history = list(warmup)[-p.slow:]
    peak, day_start = cash, cash
    day, entries, cooldown = None, 0, 0
    halted = daily_halt = False
    pending_exit = False
    rate = D(p.fee_bps)/10000
    impact = D(p.slippage_bps+p.spread_bps/2)/10000
    overhead = D(p.hourly_overhead)/12
    step = D(p.qty_step)

    def sell(ref, ts, reason):
        nonlocal cash, qty, fees, entry_cost
        fill = ref*(1-impact)
        exit_fee = qty*fill*rate
        net = qty*fill-exit_fee-entry_cost
        trades.append({'exit_timestamp':ts,'reason':reason,'quantity':float(qty),
            'entry_price':float(entry_price),'exit_price':float(fill),
            'net_pnl':float(net),'fees':float(entry_fee+exit_fee)})
        cash += qty*fill-exit_fee
        fees += exit_fee
        qty = D(0)
        entry_cost = D(0)

    for idx,r in enumerate(rows):
        ts = r['timestamp']
        op, close = D(r['open']), D(r['close'])
        eq_open = cash+qty*op
        current_day = ts//86400
        if current_day != day:
            day, day_start, entries, daily_halt = current_day, eq_open, 0, False
        peak = max(peak, eq_open)
        if strategy != 'hold' and eq_open <= peak*(1-D(p.max_drawdown)): halted=True
        if strategy != 'hold' and eq_open <= day_start*(1-D(p.daily_loss)): daily_halt=True
        want = signal(history,p,strategy)
        # Decisions see prior closed candles only; fills at this bar's open plus costs.
        exited = False
        if qty and (pending_exit or halted or daily_halt or not want):
            sell(op,ts,'risk' if pending_exit or halted or daily_halt else 'signal')
            cooldown=p.cooldown_bars
            exited=True
        pending_exit=False
        if want and not qty and not exited and not halted and not daily_halt and cooldown==0 and entries<p.max_entries_day:
            fill=op*(1+impact)
            budget=min(D(p.notional),max(D(0),cash)/(1+rate))
            size=(budget/fill/step).to_integral_value(rounding=ROUND_DOWN)*step
            if size*fill>=D(p.min_notional):
                qty=size
                entry_fee=qty*fill*rate
                entry_cost=qty*fill+entry_fee
                entry_price=fill
                cash-=entry_cost; fees+=entry_fee; entries+=1
        if cooldown>0 and not exited: cooldown-=1
        cash-=overhead
        equity=cash+qty*close
        peak=max(peak,equity)
        if strategy != 'hold' and equity<=peak*(1-D(p.max_drawdown)):
            halted=True; pending_exit=bool(qty)
        if strategy != 'hold' and equity<=day_start*(1-D(p.daily_loss)):
            daily_halt=True; pending_exit=bool(qty)
        # Boundaries: close all inventory at final close, charging exit costs.
        if idx==len(rows)-1 and qty:
            sell(close,ts+300,'end_of_test')
            equity=cash
        peak=max(peak,equity)
        curve.append({'timestamp':ts+300,'equity':float(equity),
            'cash':float(cash),'inventory_value':float(qty*close),
            'unrealized_pnl':float(qty*close-entry_cost) if qty else 0.,
            'drawdown_pct':float((peak-equity)/peak*100),
            'halted':halted,'daily_halted':daily_halt})
        history.append(float(close)); history=history[-p.slow:]
    hours=len(rows)/12
    hourly={}
    previous=p.capital
    for row in curve:
        hour=(row['timestamp']-1)//3600*3600
        hourly[hour]=hourly.get(hour,0)+(row['equity']-previous)
        previous=row['equity']
    hourly_rows=[{'hour_utc':datetime.fromtimestamp(t,timezone.utc).isoformat(),'pnl':v}
                 for t,v in hourly.items()]
    gains=sum(max(t['net_pnl'],0) for t in trades)
    losses=-sum(min(t['net_pnl'],0) for t in trades)
    pnl=float(cash)-p.capital
    summary={'strategy':strategy,'start_utc':datetime.fromtimestamp(rows[0]['timestamp'],timezone.utc).isoformat(),
        'end_utc':datetime.fromtimestamp(rows[-1]['timestamp']+300,timezone.utc).isoformat(),
        'bars':len(rows),'hours':hours,'initial_capital':p.capital,'order_notional':p.notional,
        'net_pnl':pnl,'return_pct':pnl/p.capital*100,'fees':float(fees),
        'overhead':p.hourly_overhead*hours,'closed_trades':len(trades),
        'win_rate_pct':sum(t['net_pnl']>0 for t in trades)/len(trades)*100 if trades else None,
        'profit_factor':gains/losses if losses else None,
        'max_drawdown_pct':max(r['drawdown_pct'] for r in curve),
        'average_pnl_per_hour':pnl/hours,'average_pnl_per_second':pnl/(hours*3600),
        'worst_hour_pnl':min(hourly.values()),'best_hour_pnl':max(hourly.values()),
        'positive_hours':sum(x>0 for x in hourly.values()),'negative_hours':sum(x<0 for x in hourly.values()),
        'halted':halted,'params':asdict(p),
        'note':'Backtest 5m; rate per second is arithmetic only, not observed second-by-second performance.'}
    return {'summary':summary,'trades':trades,'equity':curve,'hourly':hourly_rows}


def save_result(result,directory):
    path=Path(directory); path.mkdir(parents=True,exist_ok=True)
    (path/'summary.json').write_text(json.dumps(result['summary'],indent=2,allow_nan=False)+'\n')
    for name in ('trades','equity','hourly'):
        rows=result[name]
        with (path/(name+'.csv')).open('w',newline='') as f:
            if rows:
                writer=csv.DictWriter(f,fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv'); parser.add_argument('--output',default='results/custom')
    parser.add_argument('--fee-bps',type=float,default=10)
    parser.add_argument('--overhead-hour',type=float,default=0)
    args=parser.parse_args()
    result=simulate(read_candles(args.csv),Params(fee_bps=args.fee_bps,hourly_overhead=args.overhead_hour))
    save_result(result,args.output); print(json.dumps(result['summary'],indent=2))
if __name__=='__main__': main()
