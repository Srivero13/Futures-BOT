import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import research_hourly_trend as trend
from engine_v1.dataset import sha256


def rows(n):
    return [dict(timestamp=i*60000, open='100', close='100', high='100',
                 low='100', volume='1') for i in range(n)]


class HourlyTrendTests(unittest.TestCase):
    def test_direction_grid_and_cost_filter(self):
        x = [0, 0, .01, .001, 0, 0]
        self.assertTrue(trend.should_enter(x, 3600000, 0))
        self.assertFalse(trend.should_enter(x, 3660000, 0))
        x[2] = -.01
        self.assertFalse(trend.should_enter(x, 3600000, 0))
        x[2] = .001
        self.assertFalse(trend.should_enter(x, 3600000, 0))
        self.assertAlmostEqual(trend.movement_floor(), 52.00001369333, places=7)
        self.assertAlmostEqual(trend.threshold_from_scores(list(range(100))), 94.05)

    def test_calibration_causality_and_gap_rejection(self):
        data = rows(6121)
        first = trend.calibrate(data, 3600000, 6060*60000)
        data[-1].update(close='200', high='200')
        self.assertEqual(first, trend.calibrate(data, 3600000, 6060*60000))
        self.assertEqual(first['grid_examples'], 100)
        with self.assertRaises(ValueError):
            trend.calibrate(data[50:], 3600000, 6060*60000)

    def test_actual_execution_delay_horizon_costs_and_future_causality(self):
        data = rows(240)
        data[59].update(close='102', high='102')
        result = trend.evaluate(data, 3600000, 240*60000,
                                {'threshold': 0, 'end_ms': 3600000})
        trades = result['trades']
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]['decision_ms'], 3600000)
        self.assertEqual(trades[0]['entry_ms'], 61*60000)
        self.assertEqual(trades[0]['exit_ms'], 121*60000)
        self.assertLess(float(trades[0]['net_pnl']), 0)
        self.assertGreater(float(trades[0]['fees']), 0)
        self.assertNotIn('cost_gate_candidates', result['summary'])
        # Changing the entry candle's close cannot affect the preceding decision.
        data[61].update(close='90', low='90')
        changed = trend.evaluate(data, 3600000, 240*60000,
                                 {'threshold': 0, 'end_ms': 3600000})
        self.assertEqual(changed['trades'][0], trades[0])

    def test_reserved_period_blocked_before_data_read(self):
        with patch.object(trend, 'candles') as read:
            with self.assertRaisesRegex(ValueError, 'reserved'):
                trend.run([], 'ETHUSDT', '2026-08-01', 2, '2026-09-01', Path('unused.json'))
            read.assert_not_called()

    def test_protocol_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            p = root/'data.csv'
            p.write_text('fixture')
            p.with_suffix('.json').write_text(json.dumps(dict(last_open_ms=1000,
                sha256=sha256(p), venue='binance', symbol='ETHUSDT', timeframe_ms=60000)))
            cal = {'threshold': 1, 'grid_examples': 100, 'end_ms': 0}
            result = trend.evaluate(rows(240), 3600000, 240*60000, cal)
            output = root/'result.json'
            with patch.object(trend, 'calibrate', return_value=cal), \
                 patch.object(trend, 'evaluate', return_value=result), patch('sys.stdout'):
                trend.run([p], 'ETHUSDT', '2026-03-01', 1, '2026-09-01', output)
            protocol = json.loads(output.read_text())['protocol']
            self.assertEqual(protocol['horizon_minutes'], 60)
            self.assertEqual(protocol['costs']['fee_bps'], 10)
            self.assertEqual(protocol['past_momentum_floor_log_bps'], trend.movement_floor())
            with self.assertRaisesRegex(ValueError, 'exists'):
                trend.run([p], 'ETHUSDT', '2026-03-01', 1, '2026-09-01', output)
