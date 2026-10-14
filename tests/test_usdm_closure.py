import copy
from datetime import date
import unittest
from download_usdm_funding import timestamp
from usdm_sequence_accounting import account_sequence
from close_usdm_experiment import combine,run
from review_usdm_experiment import FIELDS


class ClosureTests(unittest.TestCase):
    def report(self,day,exit_price='99'):
        t=timestamp(day)
        plan=[dict(id=str(day),quantity='1',entry_ms=t,exit_ms=t+180000,entry_reference='100',exit_reference=exit_price)]
        marks=[dict(open_ms=t+i*60000,close='100',low='100',high='100') for i in range(3)]
        ledger=account_sequence(plan,marks,[],'0','0')
        summary={k:ledger[k] for k in FIELDS}
        summary.update(closed_trades=1,long_trades=1,short_trades=0,net_pnl_excluding_best_trade='0',boundary_candidates_not_evaluated=0)
        return dict(experiment='UM01',status='development_only',approved=False,ledger=ledger,summary=summary)

    def test_failed_original_is_retained_even_if_extension_wins(self):
        r=combine(self.report(date(2026,8,1)),self.report(date(2026,8,8),'110'))
        self.assertEqual(r['totals']['net_pnl'],'9')
        self.assertEqual(r['status'],'closed_rejected_development')
        self.assertEqual(r['net_excluding_best_trade'],'-1')
        self.assertNotIn('max_drawdown',r)

    def test_duplicate_and_out_of_window_rejected(self):
        first=self.report(date(2026,8,1));other=self.report(date(2026,8,8))
        other['ledger']['trades'][0]['id']=first['ledger']['trades'][0]['id']
        with self.assertRaises(ValueError): combine(first,other)
        with self.assertRaises(ValueError): combine(first,self.report(date(2026,9,1)))
        with self.assertRaises(ValueError): run(['same.json','same.json'])

    def test_exact_two_run_totals(self):
        r=combine(self.report(date(2026,8,1)),self.report(date(2026,8,8)))
        self.assertEqual(r['closed_trades'],2);self.assertEqual(r['totals']['net_pnl'],'-2')
        self.assertFalse(r['approved'])

    def test_mixed_experiment_closure_rejected(self):
        first=self.report(date(2026,8,1));other=self.report(date(2026,8,8))
        other['experiment']='UM02'
        with self.assertRaises(ValueError): combine(first,other)
