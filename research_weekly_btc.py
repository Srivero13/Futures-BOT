"""WBC01 fixed weekly BTC spot control. Development only; no orders."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import json
from pathlib import Path

from engine_v1.dataset import candles, sha256
from engine_v1.research_artifacts import read_json

D=Decimal
MINUTE=60000
WEEK=7*24*60*MINUTE
START=1704672000000  # 2024-01-08 00:00 UTC
END=1788220800000    # 2026-09-01 00:00 UTC
PROTOCOL=Path(__file__).parent/'research_protocols/weekly_btc_control_v1.json'


def build_schedule(rows,start=START,end=END):
    warmup=start-WEEK-MINUTE;terminal=end-MINUTE
    expected=warmup;previous_week=None;pending=None;decisions=[];events=[];count=0
    for row in rows:
        t=row['timestamp']
        if t<warmup: continue
        if t>terminal: break
        if t!=expected: raise ValueError(f'Missing minute: expected {expected}, got {t}')
        expected+=MINUTE;count+=1
        close=D(row['close']);opening=D(row['open'])
        if pending is not None and t==pending['execution_ms']:
            events.append(dict(kind='target',timestamp=t,price=opening,long=pending['long']))
            pending=None
        if (t+MINUTE-start)%WEEK==0:
            if t+MINUTE>=start:
                if previous_week is None: raise ValueError('Missing prior week close')
                decision=dict(decision_ms=t+MINUTE,execution_ms=t+2*MINUTE,
                    last_week_close=str(close),prior_week_close=str(previous_week),long=close>previous_week)
                if decision['execution_ms']<terminal:
                    decisions.append(decision);pending=decision
            previous_week=close
        if (t+MINUTE)%(24*60*MINUTE)==0 and t>=start:
            if t==terminal:
                events.append(dict(kind='terminal',timestamp=t,price=opening))
            else: events.append(dict(kind='mark',timestamp=t+MINUTE,price=close))
        if count%200000==0: print(f'[WBC01] validated minutes={count:,}',flush=True)
    if expected!=end: raise ValueError('Incomplete warmup/development interval')
    if not events or events[-1]['kind']!='terminal': raise ValueError('Missing terminal reference')
    return decisions,sorted(events,key=lambda e:e['timestamp'])


def simulate(events,impact_bps,hold=False):
    with localcontext() as ctx:
        ctx.prec=50
        cash=D('1000');qty=D(0);fee=D('0.001');impact=D(impact_bps)/10000
        fees=D(0);impacts=D(0);trades=[];position=None;daily=[];peak=D('1000');drawdown=D(0)
        invested_ms=0;first_target=True
        for e in events:
            price=e['price'];terminal=e['kind']=='terminal'
            target=None
            if e['kind']=='target':
                target=(True if first_target else None) if hold else e['long']
                first_target=False
            if terminal: target=False
            if target is True and not qty:
                budget=D('100')
                if cash<budget: raise ValueError('Insufficient simulated cash')
                fill=price*(1+impact);qty=budget/(fill*(1+fee));commission=qty*fill*fee
                fees+=commission;impacts+=qty*(fill-price);cash-=budget
                position=dict(entry_ms=e['timestamp'],entry_price=price,entry_fill=fill,
                              entry_fee=commission,quantity=qty,entry_outlay=budget)
            elif target is False and qty:
                fill=price*(1-impact);commission=qty*fill*fee;proceeds=qty*fill-commission
                fees+=commission;impacts+=qty*(price-fill);cash+=proceeds
                trade={**position,'exit_ms':e['timestamp'],'exit_price':price,'exit_fill':fill,
                    'exit_fee':commission,'net_pnl':proceeds-position['entry_outlay'],
                    'reference_pnl':qty*(price-position['entry_price']),'forced_terminal':terminal}
                invested_ms+=e['timestamp']-position['entry_ms'];trades.append(trade);qty=D(0);position=None
            if e['kind'] in ('mark','terminal'):
                equity=cash+qty*price;peak=max(peak,equity);drawdown=max(drawdown,(peak-equity)/peak*100)
                daily.append(dict(timestamp=e['timestamp'],equity=equity,cash=cash,quantity=qty))
        net=cash-D('1000')
        if qty or abs(sum((t['net_pnl'] for t in trades),D(0))-net)>D('1e-40'):
            raise ValueError('Ledger reconciliation failed')
        periods={};prior=D('1000')
        for point in daily:
            # Ordinary marks value the day just ended; terminal is intraday.
            stamp=point['timestamp']-1
            dt=datetime.fromtimestamp(stamp/1000,timezone.utc)
            change=point['equity']-prior;prior=point['equity']
            for key in (str(dt.year),f'{dt.year}-Q{(dt.month-1)//3+1}'):
                periods[key]=periods.get(key,D(0))+change
        best=max((t['net_pnl'] for t in trades),default=D(0))
        return dict(closed_trades=len(trades),net_pnl=net,ending_cash=cash,fees=fees,
            assumed_impact_cost=impacts,reference_price_pnl=sum((t['reference_pnl'] for t in trades),D(0)),
            turnover=sum((t['quantity']*(t['entry_fill']+t['exit_fill']) for t in trades),D(0)),
            invested_ms=invested_ms,max_daily_sampled_drawdown_pct=drawdown,
            net_excluding_best_trade=net-best,period_equity_changes=periods,
            trades=trades,daily_equity=daily,accounting_reconciled=True)


def run(paths):
    protocol,protocol_hash=read_json(PROTOCOL)
    if protocol_hash!='cadb03783056b7f4a17dd043210be015641d5e34f0dcb0f7dc6991d94631c74f':
        raise ValueError('WBC01 protocol changed; require a separately reviewed experiment')
    # Constants are fixed by the reviewed protocol, not CLI tuning parameters.
    sources={};resolved=[Path(p).resolve() for p in paths]
    if not resolved or len(set(resolved))!=len(resolved): raise ValueError('Require unique input shards')
    for p in resolved:
        meta,h=read_json(p.with_suffix('.json'))
        if type(meta.get('last_open_ms')) is not int or meta['last_open_ms']>=END:
            raise ValueError('Missing range or reserved-date input')
        digest=sha256(p)
        if (meta.get('sha256'),meta.get('venue'),meta.get('symbol'),meta.get('timeframe_ms'))!=(digest,'binance','BTCUSDT',60000):
            raise ValueError('Input provenance mismatch')
        sources[str(p)]=digest;sources[str(p.with_suffix('.json'))]=h
    decisions,events=build_schedule(candles(resolved))
    base=simulate(events,'2');stress=simulate(events,'3');buyhold=simulate(events,'2',hold=True)
    failures=[]
    for condition,label in [(base['net_pnl']>0,'Nonpositive net P&L'),
        (stress['net_pnl']>0,'Nonpositive stressed P&L'),
        (base['net_excluding_best_trade']>0,'Nonpositive after best-trade removal'),
        (base['closed_trades']>=30,'Fewer than 30 completed round trips')]:
        if not condition: failures.append(label)
    if sha256(PROTOCOL)!=protocol_hash or any(sha256(p)!=h for p,h in sources.items()):
        raise ValueError('Inputs changed during run')
    return dict(approved=False,experiment='WBC01',protocol=protocol,protocol_sha256=protocol_hash,
        sources=sources,code_sha256={p:sha256(Path(__file__).parent/p) for p in
             ('research_weekly_btc.py','engine_v1/dataset.py','engine_v1/research_artifacts.py')},
        decisions=decisions,base=base,stress=stress,buy_and_hold=buyhold,cash_baseline_net_pnl='0',
        summary=dict(closed_trades=base['closed_trades'],net_pnl=base['net_pnl'],
            stress_net_pnl=stress['net_pnl'],buy_and_hold_net_pnl=buyhold['net_pnl'],
            net_excluding_best_trade=base['net_excluding_best_trade'],screen_failures=failures,
            status='screen_failed_or_insufficient' if failures else 'development_screen_only_no_approval'),
        limitations=['Previously used development data; not independent validation.',
            'Reference minute opens plus assumed costs; not actual fills.',
            'Daily sampled drawdown misses intraday extrema; exchange filters/rounding not modeled.',
            'Fixed 100-USDT entry budget, not compounded all-in returns; stress recomputes quantities.',
            'No live orders, forecast certainty or profitability approval.'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--files',nargs='+',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists() or a.output.is_symlink(): p.error('Use a new output path')
    result=run(a.files);a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as f: json.dump(result,f,default=str,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(result['summary'],default=str,indent=2))


if __name__=='__main__': main()
