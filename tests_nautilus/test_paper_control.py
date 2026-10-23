import unittest
from decimal import Decimal as D
from integrations.nautilus.paper_control import Admission, run


class PaperControlTests(unittest.TestCase):
    def gate(self):
        gate = Admission()
        gate.last = dict(A=1_000_000_000, B=1_000_000_000)
        return gate

    def test_actual_engine_accounts_gates_and_balances(self):
        report = run()
        self.assertTrue(all(report['checks'].values()))
        self.assertEqual(report['balances'], dict(A='1000.6989', B='999.70018'))
        self.assertFalse(report['real_orders'])
        self.assertFalse(report['approved'])

    def test_pending_reservation_counts_before_any_fill(self):
        gate = self.gate()
        self.assertTrue(gate.request('A', 'a', 10**9, D('100')))
        self.assertFalse(gate.request('B', 'b', 10**9, D('51')))
        self.assertEqual(gate.audit[-1]['reason'], 'global_cap')
        self.assertTrue(gate.request('B', 'b-smaller', 10**9, D('50')))
        self.assertEqual(gate.peak_reserved, D('150'))

    def test_future_or_missing_quote_blocks_entry(self):
        for quotes in ({'A': 10**9}, {'A': 10**9, 'B': 10**9+1}):
            gate = self.gate()
            gate.last = quotes
            self.assertFalse(gate.request('A', 'a', 10**9, D('100')))
            self.assertEqual(gate.audit[-1]['reason'], 'stale_quotes')

    def test_duplicate_exit_and_capacity_release_only_after_flat_confirmation(self):
        gate = self.gate()
        self.assertTrue(gate.request('A', 'enter', 10**9, D('100')))
        gate.paused = True
        self.assertTrue(gate.request('A', 'exit', 10**9, D('100'), exit=True))
        self.assertFalse(gate.request('A', 'exit2', 10**9, D('100'), exit=True))
        self.assertEqual(gate.audit[-1]['reason'], 'exit_pending')
        self.assertEqual(gate.reserved, {'A': D('100')})
        gate.confirm_flat('A')
        self.assertEqual(gate.reserved, {})
        gate.paused = False
        self.assertFalse(gate.request('A', 'enter', 10**9, D('100')))
        self.assertEqual(gate.audit[-1]['reason'], 'duplicate')

    def test_invalid_amounts_rejected(self):
        for amount in (D('NaN'), D('Infinity'), D('-1'), 100.0):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                self.gate().request('A', 'a', 10**9, amount)


if __name__ == '__main__':
    unittest.main()
