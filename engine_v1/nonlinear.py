"""Degree-two Ridge model: six causal features plus 21 squared/interaction terms."""
from dataclasses import dataclass
import json
import numpy as np
from .model import FEATURES, RidgeModel

PAIRS = tuple((i, j) for i in range(6) for j in range(i, 6))
POLYNOMIAL_FEATURES = tuple(FEATURES) + tuple(f'{FEATURES[i]}*{FEATURES[j]}' for i, j in PAIRS)


def expand(x):
    x = np.asarray(x, dtype=np.float64)
    if x.ndim != 2 or x.shape[1] != 6:
        raise ValueError('Expected N by 6 causal features')
    with np.errstate(over='ignore', invalid='ignore'):
        return np.column_stack([x] + [x[:, i] * x[:, j] for i, j in PAIRS])


@dataclass
class PolynomialModel(RidgeModel):
    features: tuple = POLYNOMIAL_FEATURES

    def batch(self, x):
        with np.errstate(over='ignore', invalid='ignore'):
            z = (expand(x) - self.mean) / self.scale
            prediction = np.sum(z * self.coef, axis=1) + self.intercept
            valid = np.isfinite(z).all(axis=1) & (np.abs(z) <= 8).all(axis=1) & np.isfinite(prediction)
        return np.where(valid, prediction, np.nan)

    def predict(self, x):
        x = np.asarray(x, dtype=np.float64)
        if x.shape != (6,):
            return None
        result = self.batch(x[None, :])[0]
        return float(result) if np.isfinite(result) else None

    @classmethod
    def load(cls, path):
        # Base loader verifies checksum, dimensions, finite values and metadata.
        model = super().load(path)
        if model.volatility_scaled:
            raise ValueError('Polynomial schema does not support volatility scaling')
        return model


def load_model(path):
    features = json.loads(path.read_text())['model']['features']
    if features == list(POLYNOMIAL_FEATURES):
        return PolynomialModel.load(path)
    return RidgeModel.load(path)
