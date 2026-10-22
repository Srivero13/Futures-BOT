import json
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from integrations.nautilus.control import run


class NautilusControlTests(unittest.TestCase):
    def test_real_engine_reconciles_winning_and_losing_accounts(self):
        report = run()
        self.assertFalse(report['approved'])
        self.assertFalse(report['real_orders'])
        self.assertEqual([Decimal(a['ending_cash']) for a in report['accounts']],
                         [Decimal('1000.6989'), Decimal('998.7009')])
        for account in report['accounts']:
            self.assertTrue(all(account['checks'].values()))

    def test_wrong_engine_version_fails_before_replay(self):
        with patch('integrations.nautilus.control.version', return_value='2.0.0'), \
             patch('integrations.nautilus.control.run_account') as replay:
            with self.assertRaisesRegex(ValueError, 'Expected NautilusTrader'):
                run()
            replay.assert_not_called()

    def test_cli_refuses_to_replace_existing_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'report.json'
            path.write_text('{"preserve": true}')
            process = subprocess.run([sys.executable, '-m', 'integrations.nautilus.control',
                                      '--output', str(path)], capture_output=True, text=True)
            self.assertNotEqual(process.returncode, 0)
            self.assertEqual(json.loads(path.read_text()), {'preserve': True})


if __name__ == '__main__':
    unittest.main()
