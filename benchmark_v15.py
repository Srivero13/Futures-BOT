"""Equivalent-work benchmarks; no claim about network or order execution speed."""
import argparse
import json
from pathlib import Path
import platform
import statistics
import time
import numpy as np
from engine_v1.fast import FastPredictor, forecast, cost_gate
from engine_v1.model import RidgeModel
from engine_v1.operations import atomic_json


def median(fn, repeats=5):
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - start)
    return {'median_seconds': statistics.median(samples), 'samples_seconds': samples}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rows', type=int, default=100000)
    parser.add_argument('--compiled', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('reports/v1.5/benchmark.json'))
    args = parser.parse_args()
    if args.rows < 100:
        parser.error('At least 100 rows required')
    model = RidgeModel.load(Path('models/BTCUSDT-v1.json'))
    rng = np.random.default_rng(15)
    # Distinct feature vectors, no duplicated-result lookup for batch measurement.
    x = np.ascontiguousarray(rng.normal(size=(args.rows, 6)) * model.scale + model.mean)
    old = lambda: np.array([np.nan if (p := model.predict(row)) is None else p for row in x])
    predictor = FastPredictor(model, compiled=args.compiled)
    start = time.perf_counter()
    actual = predictor.batch(x)
    cold = time.perf_counter() - start
    expected = old()
    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-10, equal_nan=True)
    baseline, optimized = median(old), median(lambda: predictor.batch(x))
    costs = np.linspace(20, 50, args.rows)
    row = x[0]
    cached = forecast(model, row)
    decisions_old = median(lambda: [model.decision(row, c) for c in costs])
    decisions_new = median(lambda: [cost_gate(cached, c) for c in costs])
    for c in costs[::max(1, args.rows // 100)]:
        assert model.decision(row, c) == cost_gate(cached, c)
    report = {'version': '1.5', 'python': platform.python_version(), 'numpy': np.__version__,
              'machine': platform.machine(), 'processor': platform.processor(), 'rows': args.rows,
              'backend': 'numba' if args.compiled else 'numpy', 'cold_batch_seconds': cold,
              'v11_batch_scalar_loop': baseline, 'v15_batch': optimized,
              'batch_speedup': baseline['median_seconds'] / optimized['median_seconds'],
              'v11_repeated_quote_decisions': decisions_old, 'v15_cached_quote_decisions': decisions_new,
              'cached_quote_speedup': decisions_old['median_seconds'] / decisions_new['median_seconds'],
              'max_prediction_error_bps': float(np.nanmax(np.abs(expected - actual))),
              'scope': 'Synthetic valid float64 features; warm CPU batch throughput and repeated same-candle decisions. Excludes I/O, feature generation, ledger, network, and initial forecast for the cached workload. No total-bot or deployment-host speed claim.'}
    atomic_json(args.output, report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
