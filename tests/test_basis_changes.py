import unittest
from decimal import Decimal
from diagnose_basis_changes import analyze, reference_changes


def r(second, fb='99',fa='100'):
    return dict(kind='receipt_pair',paired_monotonic_ns=int(second*1e9),
        spot=dict(bid='100',ask='101'),usdm=dict(bid=fb,ask=fa))


class BasisChangeTests(unittest.TestCase):
    def test_static_discount_loses_spreads_in_both_directions(self):
        x=reference_changes(r(0),r(60))
        self.assertTrue(all(v<0 for v in x.values()))
        self.assertEqual(x['long_futures_short_spot'],x['long_spot_short_futures'])

    def test_convergence_has_opposite_directional_effect(self):
        x=reference_changes(r(0),r(60,'102','103'))
        self.assertAlmostEqual(float(x['long_futures_short_spot']),10000/100.5)
        self.assertAlmostEqual(float(x['long_spot_short_futures']),-50000/100.5)

    def test_fixed_grid_same_anchors_and_tail_exclusion(self):
        x=analyze(r(t) for t in range(121))
        self.assertEqual(x['paired_complete_anchors'],2)
        self.assertEqual(x['incomplete_or_late_anchors'],1)
        for h in x['horizons_seconds'].values():
            self.assertEqual(h['long_futures_short_spot']['count'],2)

    def test_late_label_excludes_anchor_at_every_horizon(self):
        x=analyze([r(0),r(5.3),r(15),r(30),r(60)])
        self.assertEqual(x['paired_complete_anchors'],0)
        self.assertIsNone(x['horizons_seconds']['5']['long_futures_short_spot']['mean_reference_change_bps'])
        with self.assertRaises(ValueError): analyze([r(5),r(0)])
