"""Offline contract tests: Nautilus is deliberately not required."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from download_v15_data import save_shard
from integrations.nautilus_bridge import load, main, validated_shards

START = 1704067200  # 2024-01-01 00:00:00 UTC


class NautilusBridgeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def shard(self, name='binance-BTCUSDT-2024-01.csv', seconds=None, prices=None,
              symbol='BTCUSDT'):
        stamps = seconds if seconds is not None else [START + i * 60 for i in range(3)]
        prices = prices if prices is not None else ['100.00000001'] * len(stamps)
        path = self.root / name
        rows = [[sec, value, '101', '99', value, '1.00000001']
                for sec, value in zip(stamps, prices)]
        save_shard(path, rows, 'synthetic-test-only', 'binance', symbol)
        return path

    def test_audit_is_read_only_and_does_not_require_nautilus(self):
        path = self.shard()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['--mode', 'audit', '--files', str(path)]), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result['bars'], 3)
        self.assertEqual(result['missing_minutes'], 0)
        self.assertEqual(result['last_close_ns'], (START + 180) * 1000000000)
        self.assertEqual(result['first_open_s'], START)
        self.assertFalse(result['approved'])
        self.assertFalse(result['real_orders'])
        self.assertFalse(result['paper_orders'])
        self.assertFalse(result['nautilus_engine_executed'])
        self.assertEqual(result['simulation_venue'], 'RESEARCH')

    def test_preserves_order_prices_and_causal_close_times(self):
        path = self.shard(prices=['100.00000001', '100.1', '100.00000002'])
        values, gaps, _ = load([path])
        self.assertEqual([v.open_second for v in values], [START, START + 60, START + 120])
        self.assertEqual([v.close_ns for v in values],
                         [(START + 60 + 60 * n) * 1000000000 for n in range(3)])
        self.assertEqual(str(values[0].close), '100.00000001')
        self.assertEqual(gaps, 0)

    def test_missing_minutes_are_explicit_and_never_synthesized(self):
        path = self.shard(seconds=[START, START + 180])
        with self.assertRaisesRegex(ValueError, 'Missing minute'):
            load([path])
        values, gaps, _ = load([path], allow_gaps=True)
        self.assertEqual(len(values), 2)
        self.assertEqual(gaps, 2)

    def test_shard_overlap_rejected(self):
        one = self.shard('one.csv')
        two = self.shard('two.csv', seconds=[START + 120, START + 180])
        with self.assertRaisesRegex(ValueError, 'Overlapping'):
            load([one, two])

    def test_truncated_shards_and_mutated_sidecars_rejected(self):
        path = self.shard()
        path.write_text(path.read_text().replace('100.00000001', '100.00000002', 1))
        with self.assertRaisesRegex(ValueError, 'checksum'):
            load([path])
        other = self.shard('other.csv')
        sidecar = other.with_suffix('.json')
        metadata = json.loads(sidecar.read_text())
        metadata['rows'] += 1
        sidecar.write_text(json.dumps(metadata))
        with self.assertRaisesRegex(ValueError, 'row count'):
            load([other])

    def test_wrong_venue_or_symbol_rejected(self):
        path = self.shard()
        with self.assertRaisesRegex(ValueError, 'identity'):
            load([path], symbol='ETHUSDT')
        sidecar = path.with_suffix('.json')
        metadata = json.loads(sidecar.read_text())
        metadata['venue'] = 'coinbase'
        sidecar.write_text(json.dumps(metadata))
        with self.assertRaisesRegex(ValueError, 'identity'):
            validated_shards([path], 'BTCUSDT')

    def test_memory_budget_is_enforced(self):
        path = self.shard()
        with self.assertRaisesRegex(ValueError, 'Memory budget'):
            load([path], max_bars=2)
        with self.assertRaisesRegex(ValueError, 'positive integer'):
            load([path], max_bars=0)

    def test_nan_precision_and_ohlc_are_rejected(self):
        samples = [
            ('NaN', 'Invalid'),
            ('100.000000001', '8 decimal'),
            ('102', 'Inconsistent OHLC'),
        ]
        for idx, (bad, error) in enumerate(samples):
            with self.subTest(bad=bad):
                path = self.root / f'invalid-{idx}.csv'
                rows = [[START, bad, '101', '99', bad, '1']]
                # save_shard validates its source; deliberately create a corrupt
                # but checksummed fixture with otherwise valid metadata.
                good = self.shard(f'good-{idx}.csv', seconds=[START])
                path.write_text(good.read_text().replace('100.00000001', bad))
                from engine_v1.dataset import sha256
                meta = json.loads(good.with_suffix('.json').read_text())
                meta['sha256'] = sha256(path)
                meta['bytes'] = path.stat().st_size
                path.with_suffix('.json').write_text(json.dumps(meta))
                with self.assertRaisesRegex(ValueError, error):
                    load([path])

    def test_absent_source_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'At least one'):
            load([])
        with self.assertRaisesRegex(ValueError, 'canonical'):
            load([self.root / 'missing.csv'])
        bare = self.root / 'bare.csv'
        bare.write_text('timestamp,open,high,low,close,volume\n')
        with self.assertRaisesRegex(ValueError, 'provenance'):
            load([bare])


if __name__ == '__main__':
    unittest.main()
