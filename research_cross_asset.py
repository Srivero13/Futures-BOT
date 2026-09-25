"""Fixed paired ETH-only versus ETH-plus-BTC hourly forecast experiment."""
import argparse
from collections import deque
from dataclasses import asdict
from itertools import zip_longest
import json
import math
from pathlib import Path

import numpy as np
from backtest_v16 import Costs
from engine_v1.dataset import candles, sha256
from engine_v1.model import FEATURES, feature_matrix
from engine_v1.operations import atomic_json, process_lock
from train_delayed_microstructure import fit_arrays, predict
from train_v15 import timestamp
from walkforward_v16 import folds, average_ranks, correlation

MINUTE = 60000
EXTRA = ['btc_return_1', 'btc_momentum_5', 'btc_momentum_20', 'eth_minus_btc_momentum_20']


def paired_examples(eth_rows, btc_rows, reserve_ms):
    """83 consecutive bars: features 0..20, decision 21, entry 22, exit 82."""
    history = deque(maxlen=83)
    previous = None
    result = []
    counts = {'aligned_minutes': 0, 'gaps': 0, 'hourly_examples': 0}
    for eth, btc in zip_longest(eth_rows, btc_rows):
        if eth is None or btc is None or eth['timestamp'] != btc['timestamp']:
            raise ValueError('BTC/ETH minute coverage differs; no silent join or forward-fill')
        ts = eth['timestamp']
        if ts >= reserve_ms:
            raise ValueError('Input enters reserved dates')
        if previous is not None:
            if ts <= previous:
                raise ValueError('Unordered candles')
            if ts-previous != MINUTE:
                history.clear()
                counts['gaps'] += 1
        previous = ts
        history.append((eth, btc))
        counts['aligned_minutes'] += 1
        if counts['aligned_minutes'] % 131072 == 0:
            print(f"[cross-asset] aligned minutes={counts['aligned_minutes']:,}", flush=True)
        if len(history) != 83 or (ts-61*MINUTE) % (60*MINUTE):
            continue
        window = list(history)
        decision = window[21][0]['timestamp']
        if decision % (60*MINUTE):
            continue
        x = feature_matrix([r[0] for r in window[:21]])[-1]
        b = feature_matrix([r[1] for r in window[:21]])[-1]
        target = math.log(float(eth['open'])/float(window[22][0]['open']))*10000
        result.append([decision, ts, *x, *b[:3], x[2]-b[2], target])
        if len(result) > 100000:
            raise ValueError('Hourly sample cap exceeded')
    if not result:
        raise ValueError('No paired hourly samples')
    data = np.asarray(result, dtype=float)
    if not np.isfinite(data).all():
        raise ValueError('Non-finite paired examples')
    counts['hourly_examples'] = len(data)
    return data, counts


def cost_threshold():
    c = Costs()
    f = c.fee_bps/10000
    s = (c.spread_bps/2+c.slippage_bps)/10000
    return 10000*(math.log1p(f)-math.log1p(-f)+math.log1p(s)-math.log1p(-s))+c.margin_bps


def split(data, start, end):
    # Purge every row whose outcome reaches the next partition.
    return data[(data[:, 0] >= start) & (data[:, 1] < end)]


def compare_fold(train, calibration, test):
    if min(len(train), len(calibration), len(test)) < 100 or len(train) < 1000:
        raise ValueError('Require >=1000 training and >=100 calibration/test paired samples')
    summary = {'training_samples': len(train), 'calibration_samples': len(calibration),
               'test_samples': len(test), 'zero_rmse_log_bps': float(np.sqrt(np.mean(test[:, -1]**2))),
               'models': {}}
    weights, predictions = {}, {}
    for name, stop in (('eth_only', 8), ('eth_plus_btc', 12)):
        model = fit_arrays(train[:, 2:stop], train[:, -1])
        cal_p = predict(calibration[:, 2:stop], model)
        p = predict(test[:, 2:stop], model)
        if not np.isfinite(cal_p).all() or not np.isfinite(p).all():
            raise ValueError('Non-finite forecasts')
        cutoff = float(np.quantile(cal_p, .8))
        buffer = max(0., float(np.quantile(cal_p-calibration[:, -1], .9)))
        selected = (p >= cutoff) & (p > 0)
        eligible = p-buffer > cost_threshold()
        y = test[:, -1]
        summary['models'][name] = {
            'rmse_log_bps': float(np.sqrt(np.mean((p-y)**2))),
            'spearman': correlation(average_ranks(p), average_ranks(y)),
            'calibration_top_cutoff_log_bps': cutoff,
            'calibration_downside_buffer_log_bps': buffer,
            'selected_samples': int(selected.sum()),
            'selected_mean_reference_return_log_bps': float(y[selected].mean()) if selected.any() else None,
            'cost_gate_candidates': int(eligible.sum()),
            'cost_gate_mean_reference_return_log_bps': float(y[eligible].mean()) if eligible.any() else None,
        }
        weights[name], predictions[name] = model, p.tolist()
    summary['btc_minus_eth_rmse_log_bps'] = summary['models']['eth_plus_btc']['rmse_log_bps']-summary['models']['eth_only']['rmse_log_bps']
    return {'summary': summary, 'weights': weights, 'predictions': predictions,
            'decision_ms': test[:, 0].astype(np.int64).tolist(),
            'label_end_ms': test[:, 1].astype(np.int64).tolist(),
            'actual_reference_return_log_bps': test[:, -1].tolist()}


def verify(paths, symbol, reserve):
    paths = [Path(p).resolve() for p in paths]
    if not paths or len(set(paths)) != len(paths):
        raise ValueError('Require unique chronological input files')
    sources = []
    for path in paths:
        sidecar = path.with_suffix('.json')
        meta_hash = sha256(sidecar)
        meta = json.loads(sidecar.read_text())
        digest = sha256(path)
        if (meta.get('sha256'), meta.get('venue'), meta.get('symbol'), meta.get('timeframe_ms')) != (digest, 'binance', symbol, MINUTE):
            raise ValueError(f'Provenance mismatch: {path.name}')
        if type(meta.get('last_open_ms')) is not int or meta['last_open_ms'] >= reserve:
            raise ValueError('Shard enters reserve or lacks range metadata')
        sources.append({'path': str(path), 'sha256': digest,
                        'sidecar': str(sidecar), 'sidecar_sha256': meta_hash})
    return paths, sources


def run(eth, btc, first_test, months, reserve_from, output):
    schedule = folds(first_test, months)
    reserve = timestamp(reserve_from)
    if timestamp(schedule[-1]['test_end']) > reserve:
        raise ValueError('Evaluation crosses reserved dates')
    protocol_path = output.with_suffix('.protocol.json')
    if output.exists() or protocol_path.exists():
        raise ValueError('Output/protocol exists; choose a new filename')
    print('[cross-asset] verifying both input series', flush=True)
    eth, es = verify(eth, 'ETHUSDT', reserve)
    btc, bs = verify(btc, 'BTCUSDT', reserve)
    root = Path(__file__).parent
    code = {p: sha256(root/p) for p in ('research_cross_asset.py', 'engine_v1/dataset.py',
            'engine_v1/model.py', 'train_delayed_microstructure.py', 'walkforward_v16.py',
            'backtest_v16.py', 'train_v15.py')}
    protocol = {'hypothesis': 'Past BTC returns add predictive value to ETH-only features',
        'market': 'binance_spot', 'target_symbol': 'ETHUSDT', 'context_symbol': 'BTCUSDT',
        'base_features': FEATURES, 'extra_features': EXTRA, 'alpha': 10,
        'decision_grid_minutes': 60, 'entry_delay_minutes': 1, 'holding_minutes': 60,
        'target': 'delayed ETH open-to-open log-bps before costs',
        'schedule': schedule, 'reserve_from': reserve_from, 'costs': asdict(Costs()),
        'cost_plus_margin_log_bps': cost_threshold(), 'sources': es+bs, 'code_sha256': code,
        'status': 'Fixed retrospective development comparison, not an untouched holdout'}
    atomic_json(protocol_path, protocol)
    data, counts = paired_examples(candles(eth), candles(btc), reserve)
    results = []
    for i, fold in enumerate(schedule, 1):
        print(f"[cross-asset] fold {i}/{months}: {fold['calibration_end']}", flush=True)
        a, b, c = (timestamp(fold[k]) for k in ('train_end', 'calibration_end', 'test_end'))
        result = compare_fold(split(data, 0, a), split(data, a, b), split(data, b, c))
        result.update(fold)
        results.append(result)
        print(json.dumps(result['summary']), flush=True)
    for source in es+bs:
        if sha256(source['path']) != source['sha256'] or sha256(source['sidecar']) != source['sidecar_sha256']:
            raise ValueError('Inputs changed during research')
    n = sum(r['summary']['test_samples'] for r in results)
    pooled = lambda key: math.sqrt(sum(r['summary']['test_samples']*key(r['summary'])**2 for r in results)/n)
    summary = {'folds': len(results), 'paired_test_samples': n,
        'btc_beats_eth_rmse_folds': sum(r['summary']['btc_minus_eth_rmse_log_bps'] < 0 for r in results),
        'pooled_zero_rmse_log_bps': pooled(lambda s: s['zero_rmse_log_bps']),
        'models': {name: {
            'pooled_rmse_log_bps': pooled(lambda s: s['models'][name]['rmse_log_bps']),
            'folds_beating_zero': sum(r['summary']['models'][name]['rmse_log_bps'] < r['summary']['zero_rmse_log_bps'] for r in results),
            'cost_gate_candidates': sum(r['summary']['models'][name]['cost_gate_candidates'] for r in results),
        } for name in ('eth_only', 'eth_plus_btc')}}
    atomic_json(output, {'approved': False, 'pnl': None, 'protocol': protocol,
        'alignment': counts, 'summary': summary, 'folds': results,
        'limitations': [
            'Previously inspected months are development data. Added BTC features do not create an independent holdout.',
            'Labels use delayed reference opens; no order-book fills, volume constraints or portfolio accounting.',
            'Closed-bar availability at decision time is assumed, not verified by historical receipt timestamps.',
            'Calibration residual quantile is a heuristic buffer, not a guaranteed confidence bound under dependence or drift.',
            'No OOD filtering; predictions may extrapolate. Identical rows used for both models and zero baseline.',
            'Correlation and RMSE are forecast diagnostics, not evidence of economic viability or promotion.',
        ]})
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--eth-files', nargs='+', type=Path, required=True)
    p.add_argument('--btc-files', nargs='+', type=Path, required=True)
    p.add_argument('--first-test', required=True)
    p.add_argument('--months', type=int, default=6)
    p.add_argument('--reserve-from', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    try:
        with process_lock(a.output.with_suffix('.lock')):
            summary = run(a.eth_files, a.btc_files, a.first_test, a.months, a.reserve_from, a.output)
        print(json.dumps(summary, indent=2))
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as exc:
        p.exit(2, f'Cross-asset research stopped: {exc}\n')


if __name__ == '__main__':
    main()
