"""Nautilus 2.x smoke test. Runs ONLY in the isolated Python 3.13 CI job."""
import unittest
import tempfile
from pathlib import Path

from download_v15_data import save_shard
from integrations.nautilus_bridge import load, replay


class NativeReplayTests(unittest.TestCase):
    def test_actual_engine_receives_causally_timestamped_bars(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'binance-BTCUSDT-2024-01.csv'
            start = 1704067200
            rows = [[start + 60 * i, '42000.00000000', '42100',
                     '41900', '42000.00000000', '1.25000000'] for i in range(26)]
            save_shard(path, rows, 'synthetic-test-only', 'binance', 'BTCUSDT')
            candles, gaps, _ = load([path])
            self.assertEqual(gaps, 0)
            result = replay(candles, 'BTCUSDT')
            self.assertTrue(result['nautilus_engine_executed'])
            self.assertEqual(result['dispatched_bars'], len(candles))


if __name__ == '__main__':
    unittest.main()
