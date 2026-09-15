import csv
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from download_v15_data import coinbase_rows, save_shard, verified
from engine_v1.dataset import examples, segment
from engine_v1.fast import FastPredictor, forecast, cost_gate
from engine_v1.model import RidgeModel, feature_matrix
from engine_v1.training import Reservoir, fit_stream


class V15Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        rng = np.random.default_rng(15)
        close = 100 * np.exp(np.cumsum(rng.normal(0, .001, 700)))
        self.rows = [{'timestamp': i * 60000, 'open': str(c), 'high': str(c * 1.002),
                      'low': str(c * .998), 'close': str(c), 'volume': str(10 + i % 13)} for i, c in enumerate(close)]
        self.path = self.write('data.csv', self.rows)
        self.model = RidgeModel('BTCUSDT', 3, [0]*6, [1]*6, [1,2,3,4,5,6], .1, .2, 0, 1, 100, 30, 1, 1)

    def write(self, name, rows):
        path = self.root / name
        with path.open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            for r in rows:
                writer.writerow({**r, 'timestamp': r['timestamp'] // 1000})
        return path

    def test_chunks_equal_full_features_and_next_open_labels(self):
        batch = np.concatenate(list(examples([self.path], 3, 32)))
        x = feature_matrix(self.rows)
        np.testing.assert_allclose(batch[:, 2:8], x[20:-4], atol=1e-12)
        expected = [np.log(float(self.rows[i+4]['open']) / float(self.rows[i+1]['open']))*10000 for i in range(20, 696)]
        np.testing.assert_allclose(batch[:, -1], expected, atol=1e-10)
        np.testing.assert_array_equal(batch[:, 0], np.arange(21, 697)*60000)

    def test_shard_boundaries_do_not_change_features(self):
        paths = [self.write('a.csv', self.rows[:327]), self.write('b.csv', self.rows[327:])]
        np.testing.assert_allclose(np.concatenate(list(examples(paths, 3, 64))), np.concatenate(list(examples([self.path], 3, 64))))

    def test_gap_resets_features_and_labels(self):
        path = self.write('gap.csv', self.rows[:100] + self.rows[105:])
        batch = np.concatenate(list(examples([path], 3, 32)))
        self.assertFalse(np.any((batch[:, 0] < 105*60000) & (batch[:, 1] >= 100*60000)))
        self.assertFalse(np.any((batch[:, 0] >= 105*60000) & (batch[:, 0] < 126*60000)))

    def test_overlapping_shards_rejected(self):
        with self.assertRaises(ValueError):
            list(examples([self.path, self.path]))

    def test_future_labels_are_purged(self):
        factory = lambda: examples([self.path], 3, 32)
        batch = np.concatenate(list(segment(factory, 200*60000, 400*60000)))
        self.assertTrue(np.all(batch[:, 0] >= 200*60000))
        self.assertTrue(np.all(batch[:, 1] < 400*60000))

    def test_streaming_qr_matches_full_augmented_svd(self):
        factory = lambda: examples([self.path], 3, 32)
        model, _ = fit_stream(factory, 'BTCUSDT', 3, 400*60000, 600*60000)
        b = np.concatenate(list(segment(factory, 0, 400*60000)))
        x, y = b[:, 2:8], b[:, 8]
        mean, scale = x.mean(0), x.std(0)
        scale = np.where(scale < 1e-12, 1., scale)
        expected = np.linalg.lstsq(np.vstack(((x-mean)/scale, np.sqrt(10)*np.eye(6))), np.r_[y-y.mean(), np.zeros(6)], rcond=None)[0]
        np.testing.assert_allclose(model.coef, expected, rtol=1e-9, atol=1e-10)
        self.assertFalse(model.approved)
        other, _ = fit_stream(lambda: examples([self.path], 3, 100), 'BTCUSDT', 3, 400*60000, 600*60000)
        np.testing.assert_allclose(model.coef, other.coef, atol=1e-10)

    def test_holdout_changes_cannot_change_fit_or_calibration(self):
        altered = [{**r, 'open': str(float(r['open'])*2), 'close': str(float(r['close'])*2), 'low': str(float(r['low'])*2), 'high': str(float(r['high'])*2)} if i >= 600 else r for i,r in enumerate(self.rows)]
        other = self.write('future.csv', altered)
        a, _ = fit_stream(lambda: examples([self.path]), 'BTCUSDT', 3, 400*60000, 600*60000)
        b, _ = fit_stream(lambda: examples([other]), 'BTCUSDT', 3, 400*60000, 600*60000)
        self.assertEqual(a, b)

    def test_numpy_forecasts_and_ood_match(self):
        x = np.random.default_rng(5).normal(size=(100, 6))
        x[0,0] = np.nan; x[1,1] = np.inf; x[2,2] = 8.1; x[3,2] = 8.
        for scaled in (False, True):
            self.model.volatility_scaled = scaled
            expected = [np.nan if (p := self.model.predict(row)) is None else p for row in x]
            np.testing.assert_allclose(FastPredictor(self.model).batch(x), expected, rtol=1e-12, atol=1e-10, equal_nan=True)

    def test_compiled_forecasts_match_when_installed(self):
        try:
            import numba
        except ImportError:
            self.skipTest('Optional Numba is not installed')
        x = np.random.default_rng(5).normal(size=(100, 6))
        x[0,0] = np.nan; x[1,1] = np.inf; x[2,2] = 8.1
        for scaled in (False, True):
            self.model.volatility_scaled = scaled
            np.testing.assert_allclose(FastPredictor(self.model, True).batch(x), FastPredictor(self.model).batch(x), rtol=1e-12, atol=1e-10, equal_nan=True)

    def test_cached_decision_rechecks_cost(self):
        x = np.ones(6)
        cached = forecast(self.model, x)
        for c in (0, 10, 100, -1, float('nan')):
            self.assertEqual(cost_gate(cached, c), self.model.decision(x, c))
        self.assertTrue(cost_gate(cached, 0)['enter'])
        self.assertFalse(cost_gate(cached, 100)['enter'])
        self.assertFalse(cost_gate(None, 0)['enter'])

    def test_coinbase_order_mapping_filter_and_conflict(self):
        payload = [[120, '9', '12', '10', '11', '4'], [60, '9', '12', '10', '11', '4'], [0, '9', '12', '10', '11', '4']]
        self.assertEqual(coinbase_rows(payload, 60, 120), [[60, '10', '12', '9', '11', '4']])
        with self.assertRaises(ValueError):
            coinbase_rows(payload + [[60, '9', '12', '10', '12', '4']], 60, 120)

    def test_resume_checks_hash_and_invalid_shard_not_published(self):
        path = self.root / 'shard.csv'
        save_shard(path, [[60, '10', '12', '9', '11', '4']], 'fixture', 'coinbase', 'BTC-USD')
        self.assertTrue(verified(path))
        path.write_text(path.read_text() + 'corruption')
        with self.assertRaises(ValueError): verified(path)
        invalid = self.root / 'invalid.csv'
        with self.assertRaises(ValueError):
            save_shard(invalid, [[60, '10', '8', '9', '11', '4']], 'fixture', 'coinbase', 'BTC-USD')
        self.assertFalse(invalid.exists())

    def test_reservoir_is_bounded_reproducible(self):
        a, b = Reservoir(50), Reservoir(50)
        for values in np.array_split(np.arange(10000), 100):
            a.add(values); b.add(values)
        self.assertEqual(len(a.values), 50)
        self.assertEqual(a.count, 10000)
        np.testing.assert_array_equal(a.values, b.values)

    def test_coinbase_pagination_and_resume_end_to_end(self):
        from datetime import datetime, timedelta, timezone
        from unittest.mock import patch
        from urllib.parse import urlparse, parse_qs
        from download_v15_data import coinbase
        start = datetime(2025, 10, 1, tzinfo=timezone.utc)
        def fetch(url, path, limit):
            query = parse_qs(urlparse(url).query)
            left = int(datetime.fromisoformat(query['start'][0]).timestamp())
            right = int(datetime.fromisoformat(query['end'][0]).timestamp())
            payload = [[stamp, '9', '12', '10', '11', '4'] for stamp in range(left - 60, right + 60, 60)]
            path.write_text(json.dumps(list(reversed(payload))))
        with patch('download_v15_data.fetch_file', side_effect=fetch) as download, patch('download_v15_data.time.sleep'):
            coinbase(self.root, 'BTC-USD', start, start + timedelta(days=1))
            self.assertEqual(download.call_count, 5)
            coinbase(self.root, 'BTC-USD', start, start + timedelta(days=1))
            self.assertEqual(download.call_count, 5)
        meta = json.loads((self.root / 'coinbase-BTC-USD-2025-10-01.json').read_text())
        self.assertEqual(meta['rows'], 1440)
        self.assertEqual(meta['missing_minutes'], 0)

    def test_binance_archive_checksum_and_timestamp_units(self):
        from datetime import datetime, timezone
        import hashlib
        import io
        import zipfile
        from unittest.mock import patch
        from download_v15_data import binance
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as z:
            z.writestr('BTCUSDT-1m-2025-10.csv', '1759276800000000,10,12,9,11,4\n')
        blob = buffer.getvalue()
        def fetch(url, path, limit=0):
            path.write_bytes((hashlib.sha256(blob).hexdigest() + ' archive.zip').encode() if url.endswith('.CHECKSUM') else blob)
        with patch('download_v15_data.fetch_file', side_effect=fetch):
            binance(self.root, 'BTCUSDT', datetime(2025,10,1,tzinfo=timezone.utc), datetime(2025,11,1,tzinfo=timezone.utc))
        meta = json.loads((self.root / 'binance-BTCUSDT-2025-10.json').read_text())
        self.assertEqual(meta['first_open_ms'], 1759276800000)
        self.assertEqual(meta['missing_minutes'], 44639)

    def test_mixed_source_metadata_is_rejected(self):
        from train_v15 import run
        from engine_v1.dataset import sha256
        self.path.with_suffix('.json').write_text(json.dumps({'sha256': sha256(self.path), 'venue':'coinbase', 'symbol':'BTC-USD', 'timeframe_ms':60000}))
        with self.assertRaisesRegex(ValueError, 'source identity'):
            run([self.path], 'binance', 'BTCUSDT', self.root/'output', 400*60000, 600*60000, 700*60000)

    def test_chunks_have_bounded_output_size(self):
        chunks = list(examples([self.path], chunk_size=32))
        self.assertGreater(len(chunks), 10)
        self.assertTrue(all(0 < len(b) <= 32 for b in chunks))
