from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import evaluate_weekly_btc_forward as forward
import test_weekly_btc_registration as fixtures
from register_weekly_btc_forward import register


class ForwardTests(unittest.TestCase):
    def setup_registration(self, root):
        fixtures.RegistrationTests().fixture(root)
        stamp=datetime(2026,10,21,tzinfo=timezone.utc)
        registration=register(root,now=stamp)
        path=root/'registration.json';path.write_text(json.dumps(registration))
        return path

    def test_early_evaluation_never_reads_market_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.setup_registration(Path(tmp))
            # Fixture sources are deliberately not the production code.
            with patch.object(forward,'FROZEN_CODE',()), patch.object(forward,'candles') as candles:
                status=forward.preflight(path,datetime(2026,10,22,tzinfo=timezone.utc))[2]
                self.assertEqual(status['status'],'waiting_for_fixed_window_end')
                with self.assertRaisesRegex(ValueError,'has not ended'):
                    forward.evaluate(path,['nonexistent.csv'],datetime(2026,10,22,tzinfo=timezone.utc))
                candles.assert_not_called()

    def test_frozen_code_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.setup_registration(Path(tmp))
            with self.assertRaisesRegex(ValueError,'implementation changed'):
                forward.preflight(path,datetime(2026,10,22,tzinfo=timezone.utc))

    def test_changed_plan_and_late_registration_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.setup_registration(Path(tmp))
            r=json.loads(path.read_text());r['evaluation_protocol']['configuration_budget']=2
            path.write_text(json.dumps(r))
            with self.assertRaisesRegex(ValueError,'protocol changed'):forward.preflight(path)
            path=self.setup_registration(Path(tmp))
            r=json.loads(path.read_text());r['registered_utc']='2026-10-26T00:00:00+00:00'
            path.write_text(json.dumps(r))
            with self.assertRaisesRegex(ValueError,'no backdating'):
                forward.preflight(path,datetime(2027,4,27,tzinfo=timezone.utc))

    def test_end_boundary_requires_data_not_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=self.setup_registration(Path(tmp))
            with patch.object(forward,'FROZEN_CODE',()):
                status=forward.preflight(path,datetime(2027,4,26,tzinfo=timezone.utc))[2]
                self.assertEqual(status['status'],'window_elapsed_data_validation_required')
                self.assertFalse(status['approved'])
                with self.assertRaisesRegex(ValueError,'unique candle'):
                    forward.evaluate(path,[],datetime(2027,4,26,tzinfo=timezone.utc))
