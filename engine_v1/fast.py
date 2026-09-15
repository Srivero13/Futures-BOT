"""Equivalent float64 forecasts. Accounting remains Decimal in core.py."""
import math
from copy import deepcopy
import numpy as np


def _kernel(x, mean, scale, coef, intercept, scaled, floor, horizon):
    out = np.empty(len(x), dtype=np.float64)
    for i in range(len(x)):
        value = 0.0
        valid = True
        for j in range(6):
            z = (x[i, j] - mean[j]) / scale[j]
            if not math.isfinite(z) or abs(z) > 8:
                valid = False
            value += z * coef[j]
        value += intercept
        if scaled:
            value *= max(x[i, 3], floor) * math.sqrt(horizon) * 10000
        out[i] = value if valid and math.isfinite(value) else np.nan
    return out


class FastPredictor:
    """Snapshot a model; rebuild this object after replacing the model artifact."""
    def __init__(self, model, compiled=False):
        self.model = deepcopy(model)
        self.mean = np.array(model.mean, dtype=np.float64)
        self.scale = np.array(model.scale, dtype=np.float64)
        self.coef = np.array(model.coef, dtype=np.float64)
        self.kernel = None
        if compiled:
            from numba import njit
            self.kernel = njit(cache=True, fastmath=False)(_kernel)

    def batch(self, x):
        x = np.ascontiguousarray(x, dtype=np.float64)
        if x.ndim != 2 or x.shape[1] != 6:
            raise ValueError('Expected an N by 6 feature matrix')
        m = self.model
        if self.kernel is not None:
            return self.kernel(x, self.mean, self.scale, self.coef, m.intercept,
                               m.volatility_scaled, m.volatility_floor, m.horizon_bars)
        with np.errstate(invalid='ignore', over='ignore'):
            z = (x - self.mean) / self.scale
            result = np.sum(z * self.coef, axis=1) + m.intercept
            if m.volatility_scaled:
                result *= np.maximum(x[:, 3], m.volatility_floor) * math.sqrt(m.horizon_bars) * 10000
            valid = np.isfinite(z).all(axis=1) & (np.abs(z) <= 8).all(axis=1) & np.isfinite(result)
        return np.where(valid, result, np.nan)


def forecast(model, x):
    """Compute once per closed bar, including uncertainty; None fails closed."""
    prediction = model.predict(x)
    if prediction is None:
        return None
    return prediction, prediction - model.downside_buffer_bps * model.target_scale(x)


def cost_gate(cached, cost_bps, margin_bps=2):
    cost = float(cost_bps)
    if not math.isfinite(cost) or cost < 0 or not math.isfinite(margin_bps) or margin_bps < 0:
        return {'enter': False, 'reason': 'invalid_cost'}
    if cached is None:
        return {'enter': False, 'reason': 'invalid_or_out_of_distribution'}
    prediction, lower = cached
    log_cost = math.log1p(cost / 10000) * 10000
    return {'enter': lower > log_cost + margin_bps, 'predicted_bps': prediction,
            'lower_log_bps': lower, 'cost_bps': cost, 'cost_log_bps': log_cost,
            'reason': 'calibrated_cost_gate'}
