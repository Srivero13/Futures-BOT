"""Offline one-minute model execution research; never sends orders or approves models."""
import argparse
from collections import deque
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_DOWN, localcontext
import json
import math
from pathlib import Path
import sys
import time

from engine_v1.dataset import candles, sha256
from engine_v1.model import feature_matrix
from engine_v1.nonlinear import load_model
from engine_v1.operations import atomic_json
from train_v15 import timestamp

D = lambda value: Decimal(str(value))
MINUTE = 60000


@dataclass(frozen=True)
class Costs:
    capital: float = 1000
    notional: float = 100
    fee_bps: float = 10
    spread_bps: float = 2
    slippage_bps: float = 2
    margin_bps: float = 2
    delay_bars: int = 1
    qty_step: str = '0.000001'
    min_notional: float = 5

    def validate(self):
        for key, value in asdict(self).items():
            if key not in ('qty_step', 'delay_bars') and (not math.isfinite(value) or value < 0):
                raise ValueError(f'Invalid {key}')
        if not 0 < self.notional <= self.capital or self.min_notional <= 0:
            raise ValueError('Require positive capital/notional/minimum and notional <= capital')
        if type(self.delay_bars) is not int or not 0 <= self.delay_bars <= 60:
            raise ValueError('delay_bars must be an integer in 0..60')
        if max(self.fee_bps, self.spread_bps, self.slippage_bps) >= 1000:
            raise ValueError('Cost assumptions out of range')
        if not D(self.qty_step).is_finite() or D(self.qty_step) <= 0:
            raise ValueError('Invalid quantity step')


def simulate(rows, model, start, end, costs=Costs(), progress=None, entry_rule=None):
    costs.validate()
    if start < model.calibration_end_ms or start >= end or start % MINUTE or end % MINUTE:
        raise ValueError('Require minute-aligned interval after model calibration')
    if model.timeframe_ms != MINUTE or model.horizon_bars not in (1, 3, 5, 15, 60):
        raise ValueError('Unsupported model timeframe/horizon')
    with localcontext() as context:
        context.prec = 50
        return _simulate(rows, model, start, end, costs, progress, entry_rule)


def _simulate(rows, model, start, end, c, progress, entry_rule=None):
    cash = D(c.capital)
    peak = cash
    max_drawdown = D(0)
    fee = D(c.fee_bps) / 10000
    impact = (D(c.spread_bps) / 2 + D(c.slippage_bps)) / 10000
    # Exact reference-price return required to recover both fills and fees.
    break_even = (1 + impact) * (1 + fee) / ((1 - impact) * (1 - fee))
    threshold = math.log(float(break_even)) * 10000 + c.margin_bps
    history = deque(maxlen=21)
    pending = position = None
    previous = None
    bars = signals = rejected = candidates = unfilled = 0
    fees = D(0)
    impact_cost = D(0)
    trades = []
    hourly = {}
    last_equity = cash
    final_ts = None

    def mark(ts, ref):
        nonlocal peak, max_drawdown, last_equity
        # Liquidation-value equity includes estimated exit costs while held.
        equity = cash if position is None else cash + position['qty'] * ref * (1-impact) * (1-fee)
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, (peak-equity)/peak)
        hour = (ts-1)//3600000*3600000
        hourly[hour] = hourly.get(hour, D(0)) + equity-last_equity
        last_equity = equity

    for row in rows:
        ts = row['timestamp']
        if ts >= end:
            break
        if previous is not None and ts != previous + MINUTE:
            if ts >= start:
                raise ValueError('Gap intersects evaluation interval; no invented fills across missing data')
            history.clear()
        previous = ts
        if ts < start:
            history.append(row)
            continue
        if bars == 0 and ts != start:
            raise ValueError('Missing first evaluation candle')
        bars += 1
        op = D(row['open'])
        # At this open only preceding closed candles may inform an entry.
        if position is not None and ts == position['exit_ms']:
            fill = op*(1-impact)
            exit_fee = position['qty']*fill*fee
            proceeds = position['qty']*fill-exit_fee
            cash += proceeds
            fees += exit_fee
            impact_cost += position['qty']*(op-fill)
            trades.append({'decision_ms':position['decision_ms'], 'entry_ms':position['entry_ms'],
                           'exit_ms':ts, 'quantity':str(position['qty']),
                           'entry_price':str(position['fill']), 'exit_price':str(fill),
                           'fees':str(position['entry_fee']+exit_fee),
                           'spread_slippage_cost':str(position['impact_cost']+position['qty']*(op-fill)),
                           'net_pnl':str(proceeds-position['paid'])})
            position = None
        if position is None and pending is None and len(history) == 21:
            signals += 1
            x = feature_matrix(list(history))[-1]
            if entry_rule is None:
                prediction = model.predict(x)
                if prediction is None:
                    rejected += 1
                enter = prediction is not None and prediction-model.downside_buffer_bps*model.target_scale(x) > threshold
            else:
                enter = entry_rule(x, ts)
                if type(enter) is not bool:
                    raise ValueError('Research entry rule must return a boolean')
            if enter:
                candidates += 1
                entry_ms = ts+c.delay_bars*MINUTE
                exit_ms = entry_ms+model.horizon_bars*MINUTE
                if exit_ms < end:
                    pending = {'decision_ms':ts, 'entry_ms':entry_ms, 'exit_ms':exit_ms}
                else:
                    unfilled += 1
        if pending is not None and ts == pending['entry_ms']:
            fill = op*(1+impact)
            budget = min(D(c.notional), cash/(1+fee))
            qty = (budget/fill/D(c.qty_step)).to_integral_value(rounding=ROUND_DOWN)*D(c.qty_step)
            if qty*fill >= D(c.min_notional):
                entry_fee = qty*fill*fee
                paid = qty*fill+entry_fee
                position = dict(pending, qty=qty, fill=fill, entry_fee=entry_fee, paid=paid, impact_cost=qty*(fill-op))
                impact_cost += qty*(fill-op)
                cash -= paid
                fees += entry_fee
            else:
                unfilled += 1
            pending = None
        mark(ts, op)
        mark(ts+MINUTE, D(row['close']))
        history.append(row)
        final_ts = ts+MINUTE
        if progress and bars % 4096 == 0:
            progress(bars, len(trades))
    if final_ts != end or position is not None or pending is not None:
        raise ValueError('Incomplete interval or unsettled position; no complete result published')
    pnls = [D(t['net_pnl']) for t in trades]
    pnl = cash-D(c.capital)
    if abs(sum(pnls, D(0))-pnl) > D('1e-30'):
        raise ValueError('Trade accounting does not reconcile')
    hours = D(end-start)/3600000
    gains = sum((p for p in pnls if p > 0), D(0))
    losses = -sum((p for p in pnls if p < 0), D(0))
    return {'approved':False, 'summary':{'bars':bars, 'signals_evaluated_while_flat':signals,
        'ood_rejected':rejected, 'cost_gate_candidates':candidates, 'unfilled_candidates':unfilled,
        'closed_trades':len(trades), 'initial_capital':str(c.capital), 'ending_cash':str(cash),
        'net_pnl':str(pnl), 'return_pct':float(pnl/D(c.capital)*100), 'fees':str(fees),
        'spread_slippage_cost':str(impact_cost),
        'max_drawdown_pct':float(max_drawdown*100),
        'win_rate_pct':100*sum(p>0 for p in pnls)/len(pnls) if pnls else None,
        'profit_factor':float(gains/losses) if losses else None,
        'average_pnl_per_hour':str(pnl/hours),
        'worst_hour_pnl':str(min(hourly.values())), 'best_hour_pnl':str(max(hourly.values())),
        'entry_threshold_log_bps':threshold, 'cash_baseline_net_pnl':'0'},
        'assumptions':asdict(c), 'trades':trades,
        'hourly':[{'hour_start_ms':t,'net_equity_change':str(v)} for t,v in sorted(hourly.items())],
        'limitations':['Historical spot long-only simulation; not a live execution engine or promotion criterion.',
        'Fixed spread/slippage and full fills; no order book, partial fills, market impact or exchange filter history.',
        'Delay uses whole minute bars, not measured millisecond execution latency. Zero delay is optimistic.',
        'Holding horizon starts at delayed fill; forecasts were trained on next-open returns, so delay introduces target mismatch.',
        'Drawdown sampled at opens/closes using liquidation value; intrabar drawdown is not measured.',
        'Hourly values are marked equity changes; partial boundary hours may occur. No funding, interest or infrastructure overhead.',
        'Previously inspected periods are retrospective diagnostics, not untouched holdouts.']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--files', nargs='+', type=Path, required=True)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--venue', choices=['binance'], default='binance')
    p.add_argument('--start', required=True)
    p.add_argument('--end', required=True)
    p.add_argument('--output', type=Path, required=True)
    for name in ('capital','notional','fee_bps','spread_bps','slippage_bps','margin_bps','min_notional'):
        p.add_argument('--'+name.replace('_','-'), type=float, default=getattr(Costs(),name))
    p.add_argument('--delay-bars',type=int,default=1)
    p.add_argument('--qty-step',default='0.000001')
    a = p.parse_args()
    try:
        costs = Costs(**{k:getattr(a,k) for k in Costs.__dataclass_fields__})
        costs.validate()
        paths = [f.resolve() for f in a.files]
        if len(set(paths)) != len(paths):
            raise ValueError('Duplicate input files')
        if a.output.resolve() in paths+[a.model.resolve()] or a.output.exists():
            raise ValueError('Output already exists or overlaps an input; choose a new output path')
        model_hash = sha256(a.model)
        model = load_model(a.model)
        sources = []
        print('[backtest] verifying input checksums', file=sys.stderr, flush=True)
        for path in paths:
            digest = sha256(path)
            meta = json.loads(path.with_suffix('.json').read_text())
            if (meta.get('sha256'),meta.get('venue'),meta.get('symbol'),meta.get('timeframe_ms')) != (digest,a.venue,model.symbol,MINUTE):
                raise ValueError(f'Shard provenance mismatch: {path}')
            sources.append({'file':str(path),'sha256':digest})
        began = time.monotonic()
        def progress(bars,trades):
            print(f'[backtest] bars={bars:,} trades={trades:,} elapsed={time.monotonic()-began:.1f}s',file=sys.stderr,flush=True)
        result = simulate(candles(paths), model, timestamp(a.start), timestamp(a.end), costs, progress)
        if sha256(a.model) != model_hash or any(sha256(f) != s['sha256'] for f,s in zip(paths,sources)):
            raise ValueError('Input changed during execution')
        result['spec'] = {'model_sha256':model_hash,'symbol':model.symbol,'venue':a.venue,
                          'start':a.start,'end':a.end,'sources':sources,'runner_sha256':sha256(Path(__file__))}
        atomic_json(a.output,result)
        print(json.dumps(result['summary'],indent=2))
        print(f'Completed: {a.output}; research-only, unapproved.')
        return 0
    except (ValueError,OSError,KeyError,TypeError) as error:
        print(f'Backtest stopped: {error}',file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('Interrupted; no complete report published.',file=sys.stderr)
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
