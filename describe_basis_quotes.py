"""Descriptive one-second receipt buckets from an audited quote capture."""
import argparse
from decimal import Decimal, localcontext
import json
import math
from pathlib import Path

from audit_basis_quotes import audit
from engine_v1.dataset import sha256


def quote_metrics(record):
    with localcontext() as ctx:
        ctx.prec = 40
        sb, sa = (Decimal(record['spot'][k]) for k in ('bid', 'ask'))
        fb, fa = (Decimal(record['usdm'][k]) for k in ('bid', 'ask'))
        def bps(a, b):
            return float((a.ln()-b.ln())*10000)
        return {
            'midpoint_basis_log_bps': bps(fb+fa, sb+sa),
            'futures_bid_vs_spot_ask_log_bps': bps(fb, sa),
            'futures_ask_vs_spot_bid_log_bps': bps(fa, sb),
            'spot_spread_log_bps': bps(sa, sb),
            'futures_spread_log_bps': bps(fa, fb),
        }


def describe_pairs(records):
    origin = None
    last_bucket = -1
    values = {}
    samples = 0
    for r in records:
        if r['kind'] != 'receipt_pair':
            continue
        t = r['paired_monotonic_ns']
        if origin is None:
            origin = t
        bucket = (t-origin)//1_000_000_000
        if bucket < last_bucket:
            raise ValueError('Pairs out of order')
        if bucket == last_bucket:
            continue
        last_bucket = bucket
        samples += 1
        for key, value in quote_metrics(r).items():
            if not math.isfinite(value):
                raise ValueError('Nonfinite quote metric')
            values.setdefault(key, []).append(value)
    if not samples:
        raise ValueError('No pairs')
    metrics = {}
    for key, series in values.items():
        ordered = sorted(series)
        metrics[key] = dict(count=len(series), mean=math.fsum(series)/len(series),
            min=ordered[0], max=ordered[-1],
            **{f'p{p:02d}': ordered[math.ceil(len(series)*p/100)-1] for p in (5,50,95)})
    return dict(sampled_seconds=samples, elapsed_bucket_span=last_bucket+1,
                empty_buckets_within_pair_span=last_bucket+1-samples, metrics=metrics)


def describe(root):
    root = Path(root)
    verified = audit(root)
    def records():
        for name in verified['source_hashes']:
            if name.endswith('.jsonl'):
                with (root/name).open('rb') as handle:
                    for line in handle:
                        yield json.loads(line)
    result = describe_pairs(records())
    if any(sha256(root/name) != value for name,value in verified['source_hashes'].items()):
        raise ValueError('Capture changed during description')
    return dict(approved=False, **result,
        sampling='First recorded valid pair per one-second bucket anchored at first pair; no forward fill',
        quantiles='Nearest rank', source_hashes=verified['source_hashes'],
        runner_sha256=sha256(Path(__file__)), audit_runner_sha256=verified['runner_sha256'],
        replay_helpers_sha256=verified['replay_helpers_sha256'],
        limitations=[
            'Receipt buckets are not independent samples or exchange-synchronized quotes.',
            'Bid/ask basis levels are not round-trip returns, executable arbitrage or P&L.',
            'No fees, funding, borrowing, inventory, depth, fill or legging model.',
            'Empty buckets cover only first through last pair, not the entire requested capture.',
            'Descriptive pilot only; no strategy selection or approval.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Use a new output path')
    result = describe(args.capture)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='source_hashes'}, indent=2))


if __name__ == '__main__':
    main()
