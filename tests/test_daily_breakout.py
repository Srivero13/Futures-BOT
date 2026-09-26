import copy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from engine_v1.dataset import sha256
import research_daily_breakout as research


def candles(n=1800):
    return [dict(timestamp=i*60000, open='100', close='100', high='100',
                 low='100', volume='1') for i in range(n)]


def fixture():
    rows = candles()
    rows[1499].update(close='101', high='101')
    rows[1741].update(open='102', high='102')
    return rows


class DailyBreakoutTests(unittest.TestCase):
    def test_strict_signal_excludes_signal_bar_high(self):
        rows = fixture()
        history = rows[59:1500]
        self.assertTrue(research.signal(history, 1500*60000))
        self.assertFalse(research.signal(history, 1501*60000))
        rows[1498]['high'] = '101'
        self.assertFalse(research.signal(rows[59:1500], 1500*60000))
        self.assertFalse(research.signal(history[:-1], 1500*60000))

    def test_delayed_fill_hold_accounting_and_stress(self):
        result = research.simulate(fixture(), 1500*60000, 1800*60000)
        self.assertEqual(result['summary']['closed_trades'], 1)
        trade = result['trades'][0]
        self.assertEqual(trade['decision_ms'], 1500*60000)
        self.assertEqual(trade['entry_ms'], 1501*60000)
        self.assertEqual(trade['exit_ms'], 1741*60000)
        q = Decimal(trade['quantity'])
        expected = q*(Decimal('102')*Decimal('.9997')*Decimal('.999')
                       -Decimal('100')*Decimal('1.0003')*Decimal('1.001'))
        self.assertAlmostEqual(Decimal(trade['net_pnl']), expected, places=20)
        summary = result['summary']
        self.assertAlmostEqual(Decimal(summary['net_pnl']),
            Decimal(summary['fixed_quantity_extra_slippage_bps_per_side']['0']), places=20)
        stress = [Decimal(v) for v in summary['fixed_quantity_extra_slippage_bps_per_side'].values()]
        self.assertTrue(all(a > b for a, b in zip(stress, stress[1:])))

    def test_future_close_does_not_change_entry(self):
        rows = fixture()
        original = research.simulate(rows, 1500*60000, 1800*60000)
        rows[1501].update(close='80', low='80')
        altered = research.simulate(rows, 1500*60000, 1800*60000)
        self.assertEqual(original['trades'], altered['trades'])

    def test_missing_warmup_gap_and_truncated_interval(self):
        for rows in (fixture()[100:], fixture()[:1600], fixture()[:1600]+fixture()[1601:]):
            with self.assertRaises(ValueError):
                research.simulate(rows, 1500*60000, 1800*60000)

    def test_boundary_candidates_not_filled_and_flat_market(self):
        report = research.simulate(fixture(), 1500*60000, 1700*60000)
        self.assertEqual(report['summary']['closed_trades'], 0)
        self.assertEqual(report['summary']['unfilled_candidates'], 1)
        report = research.simulate(candles(), 1500*60000, 1800*60000)
        self.assertEqual(report['summary']['rule_candidates'], 0)
        self.assertEqual(Decimal(report['summary']['net_pnl']), 0)
        report['test_start'] = '2026-03-01'
        result = research.summarize([report]*6)
        self.assertEqual(result['status'], 'insufficient_development_evidence')
        self.assertIsNone(result['net_pnl_excluding_best_trade'])

    def test_protocol_and_reserved_shards(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            p = root/'ETH.csv'
            p.write_text('fixture')
            meta = dict(sha256=sha256(p), venue='binance', symbol='ETHUSDT', timeframe_ms=60000,
                        last_open_ms=research.timestamp('2026-09-01'))
            p.with_suffix('.json').write_text(json.dumps(meta))
            with self.assertRaisesRegex(ValueError, 'reserve'):
                research.run([p], root/'reserved.json')
            meta['last_open_ms'] = 1000
            p.with_suffix('.json').write_text(json.dumps(meta))
            expected = research.simulate(fixture(), 1500*60000, 1800*60000)
            with patch.object(research, 'simulate', side_effect=lambda *a, **k: copy.deepcopy(expected)), patch('sys.stdout'):
                research.run([p], root/'report.json')
            saved = json.loads((root/'report.json').read_text())
            self.assertEqual(saved['protocol']['hold_minutes'], 240)
            self.assertEqual(saved['protocol']['lookback_minutes'], 1440)
            self.assertEqual(saved['summary']['folds'], 6)
            self.assertFalse(saved['approved'])
            with self.assertRaisesRegex(ValueError, 'exists'):
                research.run([p], root/'report.json')
