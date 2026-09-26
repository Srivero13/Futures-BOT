"""Every-minute variant of the fixed 24-hour breakout; development only."""
import argparse
from collections import deque
from dataclasses import asdict
from decimal import Decimal, ROUND_DOWN, localcontext
import json
from pathlib import Path

from backtest_v16 import Costs
from engine_v1.dataset import candles, sha256
from engine_v1.operations import atomic_json, process_lock
from research_cross_asset import verify
from research_daily_breakout import summarize
from train_v15 import timestamp
from walkforward_v16 import folds

MINUTE = 60000
LOOKBACK = 1440
HOLD = 240
D = lambda x: Decimal(str(x))


class BreakoutWindow:
    """Bounded monotonic high queue; current signal candle excluded from reference."""
    def __init__(self):
        self.clear()

    def clear(self):
        self.highs = deque()
        self.seen = 0
        self.qualifies = False

    def __len__(self):
        return min(self.seen, LOOKBACK+1)

    def append(self, row):
        high, close = D(row['high']), D(row['close'])
        if not high.is_finite() or not close.is_finite() or not 0 < close <= high:
            raise ValueError('Invalid candle prices')
        while self.highs and self.highs[0][0] < self.seen-LOOKBACK:
            self.highs.popleft()
        self.qualifies = bool(self.seen >= LOOKBACK and close > self.highs[0][1])
        while self.highs and self.highs[-1][1] <= high:
            self.highs.pop()
        self.highs.append((self.seen, high))
        self.seen += 1


def signal(history, decision):
    return bool(decision % MINUTE == 0 and len(history) == LOOKBACK+1 and history.qualifies)


def simulate(rows, start, end, progress=None):
    if not start < end or start % MINUTE or end % MINUTE:
        raise ValueError('Require increasing minute-aligned interval')
    with localcontext() as context:
        context.prec = 50
        return _simulate(rows, start, end, progress)


def _simulate(rows, start, end, progress):
    c = Costs()
    c.validate()
    fee = D(c.fee_bps)/10000
    impact = (D(c.spread_bps)/2+D(c.slippage_bps))/10000
    cash = peak = D(c.capital)
    drawdown = D(0)
    history = BreakoutWindow()
    previous = pending = position = final = None
    bars = candidates = unfilled = 0
    trades = []

    def mark(ref):
        nonlocal peak, drawdown
        equity = cash if position is None else cash+position['qty']*ref*(1-impact)*(1-fee)
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak-equity)/peak)

    for row in rows:
        ts = row['timestamp']
        if ts >= end:
            break
        if previous is not None:
            if ts <= previous:
                raise ValueError('Unordered data')
            if ts-previous != MINUTE:
                if ts >= start:
                    raise ValueError('Gap intersects evaluation; no invented fills')
                history.clear()
        previous = ts
        if ts < start:
            history.append(row)
            continue
        if bars == 0 and (ts != start or len(history) != LOOKBACK+1):
            raise ValueError('Missing evaluation start or preceding 1441-minute warm-up')
        bars += 1
        op = D(row['open'])
        if position is not None and ts == position['exit_ms']:
            fill = op*(1-impact)
            exit_fee = position['qty']*fill*fee
            proceeds = position['qty']*fill-exit_fee
            cash += proceeds
            trades.append({
                'decision_ms': position['decision_ms'], 'entry_ms': position['entry_ms'], 'exit_ms': ts,
                'quantity': str(position['qty']), 'entry_reference': str(position['reference']),
                'exit_reference': str(op), 'entry_price': str(position['fill']), 'exit_price': str(fill),
                'fees': str(position['entry_fee']+exit_fee),
                'spread_slippage_cost': str(position['qty']*(position['fill']-position['reference']+op-fill)),
                'net_pnl': str(proceeds-position['paid'])})
            position = None
        if position is None and pending is None and signal(history, ts):
            candidates += 1
            entry = ts+MINUTE
            exit_ = entry+HOLD*MINUTE
            if exit_ < end:
                pending = {'decision_ms': ts, 'entry_ms': entry, 'exit_ms': exit_}
            else:
                unfilled += 1
        if pending is not None and ts == pending['entry_ms']:
            fill = op*(1+impact)
            budget = min(D(c.notional), cash/(1+fee))
            q = (budget/fill/D(c.qty_step)).to_integral_value(rounding=ROUND_DOWN)*D(c.qty_step)
            if q*fill >= D(c.min_notional):
                entry_fee = q*fill*fee
                paid = q*fill+entry_fee
                cash -= paid
                position = dict(pending, qty=q, fill=fill, reference=op, entry_fee=entry_fee, paid=paid)
            else:
                unfilled += 1
            pending = None
        mark(op)
        mark(D(row['close']))
        history.append(row)
        final = ts+MINUTE
        if progress and bars % 4096 == 0:
            progress(bars, len(trades))
    if final != end or pending is not None or position is not None:
        raise ValueError('Incomplete evaluation or unsettled position')
    pnl = cash-D(c.capital)
    if abs(sum((D(t['net_pnl']) for t in trades), D(0))-pnl) > D('1e-25'):
        raise ValueError('Trade accounting does not reconcile')
    stress = {}
    for extra in ('0', '0.5', '1', '2'):
        s = impact+D(extra)/10000
        net = sum((D(t['quantity'])*(D(t['exit_reference'])*(1-s)*(1-fee)
                  -D(t['entry_reference'])*(1+s)*(1+fee)) for t in trades), D(0))
        stress[extra] = str(net)
    return {'approved': False, 'assumptions': asdict(c), 'trades': trades,
        'summary': {'bars': bars, 'rule_candidates': candidates, 'unfilled_candidates': unfilled,
                    'closed_trades': len(trades), 'net_pnl': str(pnl), 'ending_cash': str(cash),
                    'max_drawdown_pct': float(drawdown*100),
                    'fees': str(sum((D(t['fees']) for t in trades), D(0))),
                    'spread_slippage_cost': str(sum((D(t['spread_slippage_cost']) for t in trades), D(0))),
                    'fixed_quantity_extra_slippage_bps_per_side': stress}}


def run(paths, output):
    schedule = folds('2026-03-01', 6)
    reserve = timestamp('2026-09-01')
    protocol_path = output.with_suffix('.protocol.json')
    if output.exists() or protocol_path.exists():
        raise ValueError('Output/protocol exists; choose a new filename')
    print('[minute-breakout] verifying development inputs', flush=True)
    paths, sources = verify(paths, 'ETHUSDT', reserve)
    root = Path(__file__).parent
    protocol = {'hypothesis': 'A close beyond the prior 24-hour high may precede four-hour upward continuation',
        'symbol': 'ETHUSDT', 'market': 'binance_spot', 'lookback_minutes': LOOKBACK,
        'decision_grid_minutes': 1, 'entry_delay_minutes': 1, 'hold_minutes': HOLD,
        'sampling_variant': 'every_completed_minute; original hourly variant retained',
        'rule': 'Latest closed minute close strictly above the preceding 1440 minute highs; long-only',
        'schedule': schedule, 'reserve_from': '2026-09-01', 'costs': asdict(Costs()),
        'experiment_budget': 'One fixed rule; no parameter or feature search in this experiment',
        'screen': 'At least 30 trades, four positive months, positive excluding best trade and with extra 1 bps slippage per side',
        'sources': sources, 'code_sha256': {name: sha256(root/name) for name in
            ('research_minute_breakout.py', 'research_daily_breakout.py', 'research_cross_asset.py', 'engine_v1/dataset.py',
             'engine_v1/operations.py', 'backtest_v16.py', 'train_v15.py', 'walkforward_v16.py')}}
    atomic_json(protocol_path, protocol)
    reports = []
    for i, fold in enumerate(schedule, 1):
        print(f"[minute-breakout] fold {i}/6: {fold['calibration_end']}", flush=True)
        report = simulate(candles(paths), timestamp(fold['calibration_end']), timestamp(fold['test_end']),
            lambda bars, trades: print(f'[minute-breakout] bars={bars:,} trades={trades}', flush=True))
        report.update(test_start=fold['calibration_end'], test_end=fold['test_end'])
        reports.append(report)
        print(json.dumps(report['summary']), flush=True)
    for source in sources:
        if sha256(source['path']) != source['sha256'] or sha256(source['sidecar']) != source['sidecar_sha256']:
            raise ValueError('Source changed during experiment')
    summary = summarize(reports)
    atomic_json(output, {'approved': False, 'protocol': protocol, 'summary': summary, 'folds': reports,
        'limitations': [
            'Previously inspected months: retrospective development, not preregistered independent evidence.',
            'Fixed full fills, hypothetical quantity filters, fixed spread/slippage; no order-book or partial-fill model.',
            'Open/close drawdown omits intrabar risk. No stop-loss, financing, tax or infrastructure overhead.',
            'Monthly capital resets; summed P&L is not a compounded portfolio return.',
            'Slippage stress holds quantities, selection and times fixed, not a strategy resimulation.',
            'Development screen is an engineering filter, not a statistical significance test or approval.',
            'No trained model or AI is used; a testable rule is the benchmark before adding complexity.',
        ]})
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--files', required=True, nargs='+', type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    try:
        with process_lock(a.output.with_suffix('.lock')):
            result = run(a.files, a.output)
        print(json.dumps(result, indent=2))
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as exc:
        p.exit(2, f'Minute breakout research stopped: {exc}\n')


if __name__ == '__main__':
    main()
