from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from batch_usdm_pilot import run
from engine_v1.dataset import sha256


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.spot = self.root/'binance-ETHUSDT-2026-08.csv'
        self.spot.write_text('fixture')
        self.spot.with_suffix('.json').write_text('{}')
        self.output = self.root/'batch'

    def execute(self, end=date(2026, 8, 4)):
        return run('ETHUSDT', date(2026, 8, 2), end, date(2026, 9, 1), self.root, self.output)

    def report(self, *args):
        return dict(approved=False, matched_minutes=1440, integrity_passed=True,
                    archive_conversion_equal=True, timestamp_alignment_passed=True,
                    inputs_sha256={str(self.spot): sha256(self.spot)})

    def test_complete_only_after_two_verified_days(self):
        with patch('batch_usdm_pilot.download') as d, patch('batch_usdm_pilot.audit', side_effect=self.report):
            result = self.execute()
            self.assertEqual(d.call_count, 2)
            self.assertEqual(result['status'], 'complete')
            self.assertEqual(result['matched_minutes'], 2880)
            self.assertFalse(result['approved'])
            with self.assertRaises(FileExistsError):
                self.execute()

    def test_audit_failure_stops_before_next_download(self):
        with patch('batch_usdm_pilot.download') as d, patch('batch_usdm_pilot.audit', side_effect=ValueError('bad day')):
            with self.assertRaises(ValueError):
                self.execute()
            self.assertEqual(d.call_count, 1)
        s = json.loads((self.output/'status.json').read_text())
        self.assertEqual(s['status'], 'failed')
        self.assertEqual(s['completed_days'], [])

    def test_interrupt_preserves_verified_day(self):
        with patch('batch_usdm_pilot.download', side_effect=[None, KeyboardInterrupt()]), patch('batch_usdm_pilot.audit', side_effect=self.report):
            with self.assertRaises(KeyboardInterrupt):
                self.execute()
        s = json.loads((self.output/'status.json').read_text())
        self.assertEqual(s['status'], 'interrupted')
        self.assertEqual(len(s['completed_days']), 1)

    def test_boundaries_and_missing_inputs_fail_before_work(self):
        with patch('batch_usdm_pilot.download') as d:
            for end in (date(2026, 8, 2), date(2026, 8, 10), date(2026, 9, 2)):
                with self.assertRaises(ValueError):
                    self.execute(end)
            self.spot.unlink()
            with self.assertRaises(ValueError):
                self.execute()
            d.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_final_input_mutation_prevents_completion(self):
        original = self.report()
        def altered(*args):
            self.spot.write_text('changed')
            return original
        with patch('batch_usdm_pilot.download'), patch('batch_usdm_pilot.audit', side_effect=altered):
            with self.assertRaisesRegex(ValueError, 'input changed'):
                self.execute(date(2026, 8, 3))
        self.assertEqual(json.loads((self.output/'status.json').read_text())['status'], 'failed')
