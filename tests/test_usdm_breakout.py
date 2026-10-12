import copy
import unittest
from research_usdm_breakout import plan,near_grid


class BreakoutTests(unittest.TestCase):
    def rows(self):
        rows=[dict(timestamp=i*60000,open='100',high='101',low='99',close='100') for i in range(800)]
        # Away from the fixed settlement exclusion grid.
        rows[250].update(high='103',close='102')
        return rows

    def test_channel_excludes_current_bar_and_delayed_entry(self):
        trades,_=plan(self.rows());t=trades[0]
        self.assertEqual(t['channel_high'],'101');self.assertEqual(t['quantity'],'0.05')
        self.assertEqual(t['decision_ms'],251*60000)
        self.assertEqual(t['entry_ms'],252*60000);self.assertEqual(t['exit_ms'],492*60000)

    def test_future_changes_leave_first_decision_unchanged(self):
        rows=self.rows();first=plan(rows)[0][0]
        for row in rows[251:]: row.update(high='1001',low='999',close='1000',open='1000')
        changed=plan(rows)[0][0]
        for key in ('decision_ms','entry_ms','exit_ms','quantity','channel_high','channel_low','signal_close'):
            self.assertEqual(first[key],changed[key])

    def test_short_wick_only_no_signal_and_no_overlap(self):
        rows=self.rows();rows[250].update(low='97',high='101',close='98')
        self.assertEqual(plan(rows)[0][0]['quantity'],'-0.05')
        rows[250]['close']='100';self.assertEqual(plan(rows)[0],[])
        rows=self.rows()
        for i in range(251,490): rows[i].update(high=str(104+i),close=str(103+i))
        trades,_=plan(rows)
        self.assertEqual(len([t for t in trades if t['entry_ms']<492*60000]),1)

    def test_boundary_and_grid_guard(self):
        rows=self.rows();trades,counts=plan(rows[:300])
        self.assertEqual(trades,[]);self.assertEqual(counts['boundary_candidates_not_evaluated'],1)
        self.assertTrue(near_grid(8*3600000+120000));self.assertFalse(near_grid(8*3600000+180000))
        rows=self.rows();rows[250].update(high='101',close='100');rows[240].update(high='103',close='102')
        trades,counts=plan(rows)
        self.assertEqual(trades,[]);self.assertEqual(counts['grid_guard_skips'],1)

    def test_plan_accounts_costs_and_funding_inside_hold(self):
        from usdm_sequence_accounting import account_sequence
        from decimal import Decimal
        rows=self.rows();trades,_=plan(rows)
        marks=[dict(open_ms=r['timestamp'],low='100',high='100',close='100') for r in rows]
        events=[dict(funding_time_ms=480*60000,mark_price='100',funding_rate='0.001')]
        ledger=account_sequence(trades,marks,events,'5','2')
        self.assertTrue(ledger['accounting_reconciled'])
        self.assertEqual(ledger['assigned_funding_events'],1)
        self.assertEqual(Decimal(ledger['funding_cashflow']),Decimal('-0.005'))
        self.assertLess(Decimal(ledger['net_pnl']),0)
