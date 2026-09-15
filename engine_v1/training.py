"""Two-pass Ridge fit using streaming moments and QR, never a normal-equation inverse."""
import math
import numpy as np
from .dataset import segment
from .fast import FastPredictor
from .model import RidgeModel


class Reservoir:
    """Uniform random-priority sample; O(capacity + batch) storage."""
    def __init__(self, capacity=100000, seed=15):
        self.capacity = capacity
        self.rng = np.random.default_rng(seed)
        self.keys = np.empty(0)
        self.values = np.empty(0)
        self.count = 0

    def add(self, values):
        self.count += len(values)
        keys = np.concatenate((self.keys, self.rng.random(len(values))))
        values = np.concatenate((self.values, values))
        if len(keys) > self.capacity:
            ids = np.argpartition(keys, self.capacity - 1)[:self.capacity]
            keys, values = keys[ids], values[ids]
        self.keys, self.values = keys, values


def fit_stream(factory, symbol, horizon, train_end, calibration_end, alpha=10):
    if horizon not in (1, 3, 5) or not math.isfinite(alpha) or alpha <= 0 or not 0 < train_end < calibration_end:
        raise ValueError('Invalid fit parameters')
    n, mean, m2 = 0, np.zeros(7), np.zeros(7)
    for b in segment(factory, 0, train_end):
        values = b[:, 2:]
        count = len(values)
        local_mean = values.mean(axis=0)
        delta = local_mean - mean
        m2 += ((values - local_mean) ** 2).sum(axis=0) + delta ** 2 * n * count / (n + count)
        mean += delta * count / (n + count)
        n += count
    if n < 100:
        raise ValueError('Insufficient training examples')
    scale = np.sqrt(m2[:6] / n)
    scale = np.where(scale < 1e-12, 1., scale)
    r = np.column_stack((np.sqrt(alpha) * np.eye(6), np.zeros(6)))
    for b in segment(factory, 0, train_end):
        augmented = np.column_stack(((b[:, 2:8] - mean[:6]) / scale, b[:, 8] - mean[6]))
        r = np.linalg.qr(np.vstack((r, augmented)), mode='r')
    coef = np.linalg.lstsq(r[:, :6], r[:, 6], rcond=None)[0]
    model = RidgeModel(symbol, horizon, mean[:6].tolist(), scale.tolist(), coef.tolist(),
                       float(mean[6]), 0., train_end, calibration_end, n, 0, 0., 0., alpha)
    reservoir = Reservoir()
    squared_error = squared_zero = 0.
    count = 0
    # Calibrate all finite examples, including those later rejected by the OOD gate.
    for b in segment(factory, train_end, calibration_end):
        # Non-overlapping labels on a fixed UTC grid; gaps cannot shift the phase.
        b = b[(b[:, 0] // 60000).astype(np.int64) % horizon == 0]
        residual = (b[:, 2:8] - mean[:6]) / scale @ coef + mean[6] - b[:, 8]
        reservoir.add(residual)
        squared_error += float(residual @ residual)
        squared_zero += float(b[:, 8] @ b[:, 8])
        count += len(b)
    if count < 30:
        raise ValueError('Insufficient calibration examples')
    values = np.sort(reservoir.values)
    rank = min(len(values) - 1, math.ceil((len(values) + 1) * .9) - 1)
    model.downside_buffer_bps = max(0., float(values[rank]))
    model.calibration_rows = count
    model.calibration_rmse_bps = math.sqrt(squared_error / count)
    model.zero_forecast_rmse_bps = math.sqrt(squared_zero / count)
    return model, {'calibration_reservoir_rows': len(values), 'quantile_is_approximate': count > len(values)}


def evaluate_stream(factory, model, start, end, compiled=False):
    predictor = FastPredictor(model, compiled=compiled)
    n = accepted = covered = candidates = 0
    error = zero = 0.
    for b in segment(factory, start, end):
        prediction = predictor.batch(b[:, 2:8])
        mask = np.isfinite(prediction)
        p, y = prediction[mask], b[mask, 8]
        n += len(b)
        accepted += len(p)
        error += float(np.sum((p - y) ** 2))
        zero += float(y @ y)
        covered += int(np.sum(y >= p - model.downside_buffer_bps))
        # Screening only: fixed 26 bps arithmetic round-trip cost + 2 log-bps margin.
        candidates += int(np.sum(p - model.downside_buffer_bps > math.log1p(26 / 10000) * 10000 + 2))
    if n == 0:
        raise ValueError('No examples in requested holdout window')
    return {'examples': n, 'accepted': accepted, 'ood_rejected': n - accepted,
            'rmse_log_bps': math.sqrt(error / accepted) if accepted else None,
            'zero_rmse_log_bps_same_accepted_rows': math.sqrt(zero / accepted) if accepted else None,
            'lower_bound_coverage': covered / accepted if accepted else None,
            'cost_gate_candidates': candidates, 'cost_assumption_bps': 26,
            'pnl': None, 'note': 'Forecast diagnostics, not an execution backtest; overlapping holdout labels.'}
