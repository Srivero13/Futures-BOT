"""Bounded-memory, provenance-aware CSV shards and causal training batches."""
import csv
import gzip
import hashlib
from pathlib import Path
import numpy as np
from .core import dec
from .model import feature_matrix


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def candles(paths):
    """Canonical timestamps are UTC seconds; reject overlaps, preserve gaps."""
    last = None
    for path in paths:
        path = Path(path)
        opener = gzip.open if path.suffix == '.gz' else open
        with opener(path, 'rt', newline='') as handle:
            for row in csv.DictReader(handle):
                ts = int(row['timestamp']) * 1000
                values = {k: dec(row[k]) for k in ('open', 'high', 'low', 'close', 'volume')}
                if ts % 60000 or (last is not None and ts <= last):
                    raise ValueError('Unordered or overlapping candles')
                if min(values[k] for k in ('open', 'high', 'low', 'close')) <= 0 or values['volume'] < 0:
                    raise ValueError('Invalid candle price/volume')
                if values['low'] > min(values['open'], values['close']) or values['high'] < max(values['open'], values['close']):
                    raise ValueError('Invalid OHLC bounds')
                row['timestamp'] = ts
                last = ts
                yield row


def examples(paths, horizon=3, chunk_size=8192):
    """Yield [decision_ms, label_end_ms, six features, log_return_bps].

    Memory is proportional to chunk_size, not file size. Retain only enough
    overlap for 20-bar features and next-open labels; gaps reset the window.
    """
    if horizon not in (1, 3, 5) or not 32 <= chunk_size <= 1000000:
        raise ValueError('Invalid horizon or chunk size')
    overlap = 20 + horizon + 1
    buffer = []
    last = None

    def emit(rows):
        count = len(rows) - overlap
        if count <= 0:
            return None
        x = feature_matrix(rows)[20:20 + count]
        opens = np.array([float(r['open']) for r in rows])
        y = np.log(opens[21 + horizon:21 + horizon + count] / opens[21:21 + count]) * 10000
        t = np.array([r['timestamp'] + 60000 for r in rows[20:20 + count]])
        end = np.array([r['timestamp'] for r in rows[21 + horizon:21 + horizon + count]])
        result = np.column_stack((t, end, x, y))
        if not np.isfinite(result).all():
            raise ValueError('Non-finite training example')
        return result

    for row in candles(paths):
        if last is not None and row['timestamp'] - last != 60000:
            batch = emit(buffer)
            if batch is not None:
                yield batch
            buffer = []
        buffer.append(row)
        last = row['timestamp']
        if len(buffer) == chunk_size + overlap:
            yield emit(buffer)
            buffer = buffer[-overlap:]
    batch = emit(buffer)
    if batch is not None:
        yield batch


def segment(factory, start, end):
    for batch in factory():
        selected = batch[(batch[:, 0] >= start) & (batch[:, 1] < end)]
        if len(selected):
            yield selected
