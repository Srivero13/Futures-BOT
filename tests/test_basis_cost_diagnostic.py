from decimal import Decimal
import unittest
from diagnose_basis_costs import cost_summary, costed_changes
from diagnose_basis_changes import reference_changes


def r(t):
    return dict(kind='receipt_pair',paired_monotonic_ns=int(t*1e9),
        spot=dict(bid='100',ask='100'),usdm=dict(bid='100',ask='100'))


class BasisCostDiagnosticTests(unittest.TestCase):
    def test_zero_cost_matches_reference_and_all_four_fees_apply(self):
        entry=r(0);exit=r(60);exit['usdm']=dict(bid='101',ask='102')
        raw=reference_changes(entry,exit)
        zero=costed_changes(entry,exit,'0','0','0')
        for side in raw:
            self.assertLess(abs(raw[side]-zero[side]),Decimal('1e-30'))
        fees=costed_changes(r(0),r(60),'10','5','0')
        self.assertTrue(all(x==Decimal('-30') for x in fees.values()))

    def test_callback_preserves_selection_and_late_exclusion(self):
        result=cost_summary([r(0),r(5),r(15),r(30),r(60)],'10','5','0')
        self.assertEqual(result['reference_diagnostic']['paired_complete_anchors'],1)
        for sides in result['cost_scenario_horizons_seconds'].values():
            for metrics in sides.values():
                self.assertEqual(metrics['count'],1)
                self.assertEqual(Decimal(metrics['mean_subtotal_bps']),-30)
        result=cost_summary([r(0),r(5.3),r(15),r(30),r(60)],'10','5','0')
        self.assertEqual(result['reference_diagnostic']['paired_complete_anchors'],0)
        self.assertIsNone(result['cost_scenario_horizons_seconds']['5']['long_futures_short_spot']['mean_subtotal_bps'])

    def test_invalid_rates_fail_before_consuming_records(self):
        def records():
            raise AssertionError('must validate first')
            yield
        for fee in ('NaN','-1','10000'):
            with self.assertRaises(ValueError): cost_summary(records(),fee,'5','0')
