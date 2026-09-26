"""Count causal breakout observations at minute and hourly sampling, without outcomes."""
import argparse
from collections import deque
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

from engine_v1.dataset import candles, sha256
from engine_v1.operations import atomic_json, process_lock
from research_cross_asset import verify
from train_v15 import timestamp

MINUTE = 60000
LOOKBACK = 1440


def audit(rows, start, end):
    if not start < end or start % MINUTE or end % MINUTE:
        raise ValueError('Require increasing minute-aligned boundaries')
    highs = deque()
    previous = None
    consecutive = evaluated = 0
    monthly = {}
    for row in rows:
        ts = row['timestamp']
        decision = ts+MINUTE
        if decision >= end:
            break
        if previous is not None:
            if ts <= previous:
                raise ValueError('Unordered candles')
            if ts-previous != MINUTE:
                if decision >= start:
                    raise ValueError('Gap intersects audit interval')
                highs.clear()
                consecutive = 0
        previous = ts
        high = Decimal(row['high'])
        close = Decimal(row['close'])
        if not high.is_finite() or not close.is_finite() or not 0 < close <= high:
            raise ValueError('Invalid prices')
        while highs and highs[0][0] < ts-LOOKBACK*MINUTE:
            highs.popleft()
        if start <= decision:
            if consecutive < LOOKBACK or (evaluated == 0 and decision != start):
                raise ValueError('Missing audit start or 1440 preceding candles')
            month = datetime.fromtimestamp(decision/1000, timezone.utc).strftime('%Y-%m')
            result = monthly.setdefault(month, {'evaluated_minutes': 0,
                'hourly_observations': 0, 'breakout_minutes': 0,
                'hourly_breakout_observations': 0, 'breakouts_by_utc_minute': [0]*60})
            minute = (decision//MINUTE) % 60
            result['evaluated_minutes'] += 1
            result['hourly_observations'] += int(minute == 0)
            if close > highs[0][1]:
                result['breakout_minutes'] += 1
                result['hourly_breakout_observations'] += int(minute == 0)
                result['breakouts_by_utc_minute'][minute] += 1
            evaluated += 1
            if evaluated % 32768 == 0:
                print(f'[sampling-audit] evaluated minutes={evaluated:,}', flush=True)
        # The signal candle's own high is added only AFTER its decision check.
        while highs and highs[-1][1] <= high:
            highs.pop()
        highs.append((ts, high))
        consecutive += 1
    if evaluated != (end-start)//MINUTE:
        raise ValueError('Incomplete audit interval')
    total = sum(r['breakout_minutes'] for r in monthly.values())
    hourly = sum(r['hourly_breakout_observations'] for r in monthly.values())
    return {'evaluated_minutes': evaluated, 'breakout_minutes': total,
            'hourly_breakout_observations': hourly,
            'breakout_minutes_outside_hourly_grid': total-hourly,
            'hourly_share_of_breakout_observations': hourly/total if total else None,
            'monthly': [{'month': month, **metrics} for month, metrics in sorted(monthly.items())]}


def run(paths, output):
    if output.exists():
        raise ValueError('Output exists; choose a new filename')
    start, end = timestamp('2026-03-01'), timestamp('2026-09-01')
    print('[sampling-audit] verifying development inputs', flush=True)
    paths, sources = verify(paths, 'ETHUSDT', end)
    summary = audit(candles(paths), start, end)
    for source in sources:
        if sha256(source['path']) != source['sha256'] or sha256(source['sidecar']) != source['sidecar_sha256']:
            raise ValueError('Source changed during audit')
    atomic_json(output, {'approved': False, 'pnl': None, 'summary': summary,
        'protocol': {'start': '2026-03-01', 'end': '2026-09-01',
                     'symbol': 'ETHUSDT', 'lookback_minutes': LOOKBACK,
                     'rule': 'Closed-minute close strictly above preceding 1440 highs; signal bar excluded'},
        'sources': sources, 'runner_sha256': sha256(Path(__file__)),
        'limitations': [
            'Counts observations, not independent breakout episodes or executable trades.',
            'Consecutive breakout minutes can be related to one price move.',
            'No position, holding period, delay, costs or future return is evaluated.',
            'Hourly observations may exceed strategy candidates while that strategy holds a position.',
            'More observations do not establish better predictions or profitability.',
            'This audit neither changes the hourly protocol nor selects a new trading frequency.',
        ]})
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--files', nargs='+', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    try:
        with process_lock(a.output.with_suffix('.lock')):
            summary = run(a.files, a.output)
        print(json.dumps(summary, indent=2))
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as exc:
        p.exit(2, f'Sampling audit stopped: {exc}\n')


if __name__ == '__main__':
    main()
