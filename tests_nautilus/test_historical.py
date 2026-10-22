import csv
import json
import tempfile
import unittest
from pathlib import Path

from engine_v1.dataset import sha256
from integrations.nautilus.historical import day_start, load_day, replay


class HistoricalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'candles.csv'
        start = day_start('2026-08-01')
        self.rows = [dict(timestamp=start//1000+i*60, open='100.10', high='101.00',
                          low='99.00', close='100.20' if i%2 else '100.30', volume=str(i+1))
                     for i in range(1440)]
        self.save()

    def save(self):
        with self.path.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=self.rows[0].keys())
            writer.writeheader()
            writer.writerows(self.rows)
        self.meta = dict(sha256=sha256(self.path), venue='binance', symbol='ETHUSDT',
                         timeframe_ms=60000, rows=len(self.rows),
                         first_open_ms=self.rows[0]['timestamp']*1000,
                         last_open_ms=self.rows[-1]['timestamp']*1000)
        self.save_meta()

    def save_meta(self):
        self.path.with_suffix('.json').write_text(json.dumps(self.meta))

    def test_real_engine_preserves_1440_closed_bars_without_orders(self):
        result = replay(self.path, 'ETHUSDT', '2026-08-01')
        self.assertEqual(result['status'], 'historical_replay_passed')
        self.assertEqual(result['bars'], 1440)
        self.assertTrue(all(result['checks'].values()))
        self.assertFalse(result['approved'])

    def test_hash_and_market_identity_rejected(self):
        for key, value in [('sha256', '0'*64), ('venue', 'binance_usdm'), ('symbol', 'BTCUSDT')]:
            with self.subTest(key=key):
                self.save()
                self.meta[key] = value
                self.save_meta()
                with self.assertRaisesRegex(ValueError, 'identity/hash'):
                    load_day(self.path, 'ETHUSDT', '2026-08-01')

    def test_gap_even_with_matching_hash_rejected(self):
        del self.rows[500]
        self.save()
        with self.assertRaisesRegex(ValueError, 'Missing minute'):
            load_day(self.path, 'ETHUSDT', '2026-08-01')

    def test_precision_loss_rejected(self):
        self.rows[100]['close'] = '100.123'
        self.save()
        with self.assertRaisesRegex(ValueError, 'precision'):
            load_day(self.path, 'ETHUSDT', '2026-08-01')

    def test_reserved_day_rejected_before_file_read(self):
        with self.assertRaisesRegex(ValueError, 'reserved'):
            load_day(Path(self.temp.name)/'missing.csv', 'ETHUSDT', '2026-09-01')

    def test_sidecar_range_disagreement_rejected(self):
        self.meta['rows'] += 1
        self.save_meta()
        with self.assertRaisesRegex(ValueError, 'row count/range'):
            load_day(self.path, 'ETHUSDT', '2026-08-01')


if __name__ == '__main__':
    unittest.main()
