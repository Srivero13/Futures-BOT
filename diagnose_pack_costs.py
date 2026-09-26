"""Compare frozen quote-return diagnostics with explicitly supplied trading costs."""
import argparse
import json
import math
from pathlib import Path

from engine_v1.dataset import sha256
from engine_v1.operations import atomic_json
from summarize_feature_pack import consolidate


def barrier(fee_bps, slippage_bps):
    values = (fee_bps, slippage_bps)
    if any(not math.isfinite(v) or not 0 <= v < 10000 for v in values):
        raise ValueError('Costs must be finite and in [0, 10000) bps per side')
    f, s = (v / 10000 for v in values)
    return 10000 * (math.log1p(f) - math.log1p(-f)
                    + math.log1p(s) - math.log1p(-s))


def diagnose(summary, fee_bps, slippage_bps):
    threshold = barrier(fee_bps, slippage_bps)
    models = {}
    for name, model in summary['models'].items():
        mean = model['selected_weighted_mean_quote_log_bps']
        models[name] = {
            'selected_samples': model['selected_samples'],
            'selected_mean_quote_log_bps': mean,
            'selected_mean_minus_cost_log_bps': None if mean is None else mean - threshold,
            'frozen_cost_eligible_forecasts': model['cost_eligible_forecasts'],
        }
    return {'captures': summary['captures'], 'common_rows': summary['common_rows'],
            'scenario_cost_barrier_log_bps': threshold, 'models': models}


def run(pack_path, paths, output, fee_bps, slippage_bps):
    if output.exists():
        raise ValueError('Output exists; choose a new filename')
    barrier(fee_bps, slippage_bps)
    sources = []

    def read(path):
        digest = sha256(path)
        data = json.loads(path.read_text())
        if sha256(path) != digest:
            raise ValueError('Input changed while loading')
        sources.append({'path': str(path.resolve()), 'sha256': digest})
        return data, digest

    pack, digest = read(pack_path)
    reports = [read(path)[0] for path in paths]
    pooled, _ = consolidate(pack, digest, reports)
    summary = diagnose(pooled, fee_bps, slippage_bps)
    atomic_json(output, {
        'approved': False, 'pnl': None, 'symbol': pack['symbol'],
        'pack_sha256': digest, 'sources': sources,
        'runner_sha256': sha256(Path(__file__)),
        'cost_inputs': {'fee_bps_per_side': fee_bps,
                        'slippage_bps_per_side': slippage_bps,
                        'verification': 'User-supplied scenario; no account query'},
        'frozen_cost_barrier_log_bps': pack['cost_barrier_log_bps'],
        'summary': summary,
        'limitations': [
            'Quote targets already include ask-to-bid spread; no extra spread is charged.',
            'Same proportional fee and adverse slippage assumed on each side.',
            'Mean log-return minus cost is not expected cash P&L or an execution backtest.',
            'Selected samples differ by model; this is not a paired selection comparison.',
            'Eligibility counts belong to the original frozen cost barrier, not this scenario.',
            'Saved statistics cannot recompute scenario eligibility or confidence intervals.',
            'No model, cutoff, historical report or trading approval is changed.',
        ],
    })
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pack', required=True, type=Path)
    p.add_argument('--reports', required=True, nargs='+', type=Path)
    p.add_argument('--fee-bps-per-side', required=True, type=float)
    p.add_argument('--slippage-bps-per-side', required=True, type=float)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    try:
        result = run(a.pack, a.reports, a.output, a.fee_bps_per_side, a.slippage_bps_per_side)
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        p.exit(2, f'Cost diagnostic stopped: {exc}\n')


if __name__ == '__main__':
    main()
