"""Deterministic closed-bar feature fingerprints shared by offline and Nautilus replay.

Only the project's original six causal research features are calculated.
This module never emits trading decisions or submits orders.
"""
from collections import deque
import hashlib
import math

from engine_v1.model import feature_matrix


class ShadowDigest:
    def __init__(self):
        self.rows = deque(maxlen=21)
        self.last_open_second = None
        self.digest = hashlib.sha256()
        self.feature_windows = 0
        self.resets = 0

    def accept(self, second, *, open, high, low, close, volume):
        if type(second) is not int or second < 0 or second % 60:
            raise ValueError('Expected aligned integer minute-open UTC seconds')
        if self.last_open_second is not None:
            delta = second - self.last_open_second
            if delta <= 0:
                raise ValueError('Out-of-order closed candle')
            if delta != 60:
                self.rows.clear()
                self.resets += 1
        self.last_open_second = second
        self.rows.append({'timestamp': second * 1000, 'open': str(open),
                          'high': str(high), 'low': str(low),
                          'close': str(close), 'volume': str(volume)})
        if len(self.rows) != 21:
            return
        features = feature_matrix(list(self.rows))[-1]
        if not all(math.isfinite(float(value)) for value in features):
            raise ValueError('Non-finite causal feature')
        # Float hex is deterministic and lossless; no tolerance is silently applied.
        line = f"{(second+60)*1_000_000_000}:" + "|".join(float(v).hex() for v in features) + "\n"
        self.digest.update(line.encode('ascii'))
        self.feature_windows += 1

    def result(self):
        return {'feature_windows': self.feature_windows, 'feature_resets': self.resets,
                'feature_sha256': self.digest.hexdigest()}


def from_candles(candles):
    observer = ShadowDigest()
    for c in candles:
        observer.accept(c.open_second, open=c.open, high=c.high, low=c.low,
                        close=c.close, volume=c.volume)
    return observer.result()
