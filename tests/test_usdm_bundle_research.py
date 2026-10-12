from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from download_usdm_funding import timestamp
from research_usdm_bundle import weekly_summary,load_bundle,run


class BundleResearchTests(unittest.TestCase):
    def test_exit_boundary_week_and_no_reset(self):
        ledger=dict(net_pnl='1.25',trades=[dict(accounting=dict(exit_ms=timestamp(date(2026,8,14)),scenario_net_pnl='3')),
               dict(accounting=dict(exit_ms=timestamp(date(2026,8,15)),scenario_net_pnl='-1.75'))])
        weeks=weekly_summary(ledger)
        self.assertEqual([w['net_pnl'] for w in weeks],['3','-1.75','0','0'])
        ledger['net_pnl']='2'
        with self.assertRaises(ValueError): weekly_summary(ledger)

    def test_incomplete_manifest_rejected_before_audits(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'bundle.json').write_text(json.dumps(dict(identity={},status='running')))
            with patch('research_usdm_bundle.audit_trades') as audit:
                with self.assertRaises(ValueError): load_bundle(root)
                audit.assert_not_called()

    def test_runner_uses_fixed_costs_and_stays_unapproved(self):
        ledger=dict(trades=[],closed_trades=0,net_pnl='0',reference_price_pnl='0',assumed_fees='0',
                    assumed_price_impact_cost='0',funding_cashflow='0',max_sampled_drawdown_quote='0',accounting_reconciled=True)
        with patch('research_usdm_bundle.load_bundle',return_value=([],[],[],{})),patch('research_usdm_bundle.account_sequence',return_value=ledger) as account:
            r=run('unused')
            self.assertEqual(account.call_args.args[-2:],('5','2'))
            self.assertFalse(r['approved']);self.assertTrue(r['original_rejection_preserved'])
