import copy
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

import research_minute_breakout as minute
import research_daily_breakout as hourly
from engine_v1.dataset import sha256
import test_daily_breakout


class MinuteBreakoutTests(unittest.TestCase):
    def test_bounded_window_matches_brute_force(self):
        rng = random.Random(7)
        rows = []
        window = minute.BreakoutWindow()
        for i in range(4000):
            close = 1000+rng.randrange(100)
            row = {'high': str(close+rng.randrange(3)), 'close': str(close)}
            rows.append(row)
            window.append(row)
            expected = i >= 1440 and close > max(int(r['high']) for r in rows[i-1440:i])
            self.assertEqual(minute.signal(window, (i+1)*60000), expected)
            self.assertLessEqual(len(window.highs), 1441)
        window.clear()
        self.assertFalse(minute.signal(window, 60000))

    def test_off_hour_signal_gets_delayed_fill_and_four_hour_hold(self):
        rows = test_daily_breakout.candles()
        rows[1500].update(close='101', high='101')
        report = minute.simulate(rows, 1500*60000, 1800*60000)
        self.assertEqual(report['summary']['closed_trades'], 1)
        trade = report['trades'][0]
        self.assertEqual(trade['decision_ms'], 1501*60000)
        self.assertEqual(trade['entry_ms'], 1502*60000)
        self.assertEqual(trade['exit_ms'], 1742*60000)
        self.assertEqual(hourly.simulate(rows, 1500*60000, 1800*60000)['summary']['closed_trades'], 0)
        rows[1502].update(close='80', low='80')
        self.assertEqual(minute.simulate(rows, 1500*60000, 1800*60000)['trades'], report['trades'])

    def test_identical_execution_for_same_hourly_signal(self):
        rows = test_daily_breakout.fixture()
        self.assertEqual(minute.simulate(rows, 1500*60000, 1800*60000),
                         hourly.simulate(rows, 1500*60000, 1800*60000))

    def test_repeated_breakouts_cannot_overlap_positions(self):
        rows = test_daily_breakout.candles(2200)
        for i, row in enumerate(rows):
            price = str(100+i/100)
            row.update(open=price, high=price, low=price, close=price)
        report = minute.simulate(rows, 1500*60000, 2200*60000)
        self.assertGreater(len(report['trades']), 1)
        for a, b in zip(report['trades'], report['trades'][1:]):
            self.assertGreater(b['entry_ms'], a['exit_ms'])
        self.assertGreater(report['summary']['unfilled_candidates'], 0)

    def test_gap_and_warmup_rejected(self):
        rows = test_daily_breakout.fixture()
        for data in (rows[100:], rows[:1600]+rows[1601:]):
            with self.assertRaises(ValueError):
                minute.simulate(data, 1500*60000, 1800*60000)

    def test_separate_protocol_and_same_failure_screen(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'data.csv'
            source.write_text('fixture')
            source.with_suffix('.json').write_text(json.dumps(dict(sha256=sha256(source),
                venue='binance', symbol='ETHUSDT', timeframe_ms=60000, last_open_ms=1000)))
            report = minute.simulate(test_daily_breakout.fixture(), 1500*60000, 1800*60000)
            with patch.object(minute, 'simulate', side_effect=lambda *a, **k: copy.deepcopy(report)), patch('sys.stdout'):
                minute.run([source], root/'minute.json')
            saved = json.loads((root/'minute.json').read_text())
            self.assertEqual(saved['protocol']['decision_grid_minutes'], 1)
            self.assertEqual(saved['protocol']['hold_minutes'], 240)
            self.assertIs(minute.summarize, hourly.summarize)
            self.assertFalse(saved['approved'])
            self.assertIn('research_minute_breakout.py', saved['protocol']['code_sha256'])
            with self.assertRaises(ValueError):
                minute.run([source], root/'minute.json')
