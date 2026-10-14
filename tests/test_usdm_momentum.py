import copy
import unittest
from research_usdm_momentum import signals,plan


class MomentumTests(unittest.TestCase):
    def rows(self):
        return [dict(timestamp=i*60000,open='100',close='101' if i>=60 else '100') for i in range(240)]

    def test_closed_information_delay_and_exit(self):
        rows=self.rows();s=signals(rows)[0]
        self.assertEqual(s['decision_ms'],61*60000)
        self.assertEqual(s['entry_ms'],62*60000)
        self.assertEqual(s['exit_ms'],122*60000)
        self.assertEqual(s['quantity'],'0.05')
        t,n=plan(rows)
        self.assertEqual(t[0]['entry_reference'],'100');self.assertEqual(n,0)

    def test_future_prices_cannot_change_first_signal(self):
        rows=self.rows();expected=signals(rows[:61])[0]
        for r in rows[61:]: r['close']='1';r['open']='900'
        self.assertEqual(signals(rows)[0],expected)

    def test_short_flat_boundary_and_gaps(self):
        rows=self.rows()
        for r in rows[60:]: r['close']='99'
        self.assertEqual(signals(rows)[0]['quantity'],'-0.05')
        t,n=plan(rows[:100]);self.assertEqual(t,[]);self.assertEqual(n,1)
        for r in rows: r['close']='100'
        self.assertEqual(signals(rows),[])
        rows.pop(5)
        with self.assertRaises(ValueError): signals(rows)

    def test_plan_runs_through_sequence_accounting(self):
        from usdm_sequence_accounting import account_sequence
        rows=self.rows();trades,_=plan(rows)
        marks=[dict(open_ms=r['timestamp'],close='100',low='100',high='100') for r in rows]
        result=account_sequence(trades,marks,[],'5','2')
        self.assertEqual(result['closed_trades'],1)
        self.assertTrue(result['accounting_reconciled'])
        from decimal import Decimal
        self.assertLess(Decimal(result['net_pnl']),0)
