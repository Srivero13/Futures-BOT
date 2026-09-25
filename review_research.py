"""Build an offline evidence dossier from saved experiments; never approve trading."""
import argparse
import json
import math
from pathlib import Path

import numpy as np
from diagnose_hourly_robustness import analyze as hourly_review
from diagnose_pack_costs import diagnose as pack_costs
from engine_v1.dataset import sha256
from engine_v1.operations import atomic_json
from summarize_feature_pack import consolidate


def cross_review(report):
    if report.get('approved') is not False or report.get('pnl') is not None:
        raise ValueError('Expected unapproved cross-asset forecast report')
    if report['protocol'].get('hypothesis') != 'Past BTC returns add predictive value to ETH-only features':
        raise ValueError('Unsupported cross-asset protocol')
    totals = {'zero': 0., 'eth_only': 0., 'eth_plus_btc': 0.}
    rows = wins = 0
    prior_end = None
    for fold in report['folds']:
        y = np.asarray(fold['actual_reference_return_log_bps'], dtype=float)
        starts = np.asarray(fold['decision_ms'], dtype=np.int64)
        ends = np.asarray(fold['label_end_ms'], dtype=np.int64)
        if y.ndim != 1 or not len(y) or starts.shape != y.shape or ends.shape != y.shape:
            raise ValueError('Invalid saved prediction shapes')
        if not np.isfinite(y).all() or np.any(ends-starts != 61*60000):
            raise ValueError('Invalid delayed targets')
        # Entry is decision+1 minute; touching return intervals are allowed.
        if np.any(starts[1:]+60000 < ends[:-1]) or (prior_end is not None and starts[0]+60000 < prior_end):
            raise ValueError('Overlapping or unordered evaluation rows')
        prior_end = ends[-1]
        rows += len(y)
        totals['zero'] += float(np.dot(y, y))
        errors = {}
        for name in ('eth_only', 'eth_plus_btc'):
            p = np.asarray(fold['predictions'][name], dtype=float)
            if p.shape != y.shape or not np.isfinite(p).all():
                raise ValueError('Invalid saved predictions')
            error = float(np.dot(p-y, p-y))
            errors[name] = error
            totals[name] += error
            claimed = fold['summary']['models'][name]['rmse_log_bps']
            if not math.isclose(math.sqrt(error/len(y)), claimed, rel_tol=1e-10, abs_tol=1e-10):
                raise ValueError('Saved predictions disagree with RMSE')
        wins += errors['eth_plus_btc'] < errors['eth_only']
    if not rows or rows != report['summary']['paired_test_samples']:
        raise ValueError('Paired test count mismatch')
    rmses = {name: math.sqrt(sse/rows) for name, sse in totals.items()}
    return {'paired_test_samples': rows, 'folds': len(report['folds']),
            'recomputed_pooled_rmse_log_bps': rmses,
            'btc_beats_eth_rmse_folds': wins,
            'economic_result': 'Not an execution backtest; no P&L established'}


def run(pack_path, pack_reports, hourly_path, cross_path, output, fee, slippage):
    if output.exists():
        raise ValueError('Output exists; choose a new filename')
    sources = []

    def read(path):
        digest = sha256(path)
        value = json.loads(path.read_text())
        if sha256(path) != digest:
            raise ValueError('Source changed during read')
        sources.append({'path': str(path.resolve()), 'sha256': digest})
        return value, digest

    pack, digest = read(pack_path)
    reports = [read(path)[0] for path in pack_reports]
    summary, _ = consolidate(pack, digest, reports)
    costs = pack_costs(summary, fee, slippage)
    hourly = hourly_review(read(hourly_path)[0])
    cross = cross_review(read(cross_path)[0])
    review = {
        'approved': False, 'status': 'research_only_no_promotion_decision',
        'scope': 'Saved reports only; no reserved data read, raw replay, account query or orders',
        'sources': sources,
        'code_sha256': {name: sha256(Path(__file__).parent/name) for name in
                        ('review_research.py', 'diagnose_hourly_robustness.py',
                         'diagnose_pack_costs.py', 'summarize_feature_pack.py')},
        'cost_scenario': {'fee_bps_per_side': fee, 'slippage_bps_per_side': slippage,
                          'source': 'Explicit user-supplied rates; not independently verified'},
        'microstructure': costs, 'hourly_trend': hourly, 'cross_asset': cross,
        'research_controls': [
            'Keep inspected historical periods classified as development, including earlier designated test folds.',
            'Do not pool samples or P&L across strategies: periods and selected observations overlap.',
            'Preserve the reserved period until a candidate and evaluation protocol are fixed.',
            'Record every experiment, including failures; no threshold or feature search on reserved outcomes.',
            'A new hypothesis needs a mechanism, fixed parameters, execution assumptions and failure criteria before testing.',
        ],
        'limitations': [
            'Accounting and saved-statistic checks do not establish authenticity or raw market-data correctness.',
            'The three studies use different targets, sampling and selection; their headline metrics are not directly comparable.',
            'No profitability probability, completion percentage, confidence interval or production readiness is inferred.',
            'This dossier does not add or modify a runtime trading guard. It never grants model approval.',
        ],
    }
    atomic_json(output, review)
    return review


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pack', required=True, type=Path)
    p.add_argument('--pack-reports', required=True, nargs='+', type=Path)
    p.add_argument('--hourly-report', required=True, type=Path)
    p.add_argument('--cross-report', required=True, type=Path)
    p.add_argument('--fee-bps-per-side', required=True, type=float)
    p.add_argument('--slippage-bps-per-side', required=True, type=float)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    try:
        review = run(a.pack, a.pack_reports, a.hourly_report, a.cross_report, a.output,
                     a.fee_bps_per_side, a.slippage_bps_per_side)
        print(json.dumps({'status': review['status'], 'approved': False,
            'microstructure': review['microstructure'],
            'hourly_net_pnl': review['hourly_trend']['net_pnl'],
            'hourly_excluding_best_trade': review['hourly_trend']['net_pnl_excluding_best_trade'],
            'cross_asset': review['cross_asset']}, indent=2))
        print(f'Completed: {a.output}; evidence review only.')
    except (ValueError, KeyError, TypeError, OSError) as exc:
        p.exit(2, f'Research review stopped: {exc}\n')


if __name__ == '__main__':
    main()
