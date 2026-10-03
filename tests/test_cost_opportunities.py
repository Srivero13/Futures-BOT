import math
import unittest
from audit_cost_opportunities import audit,barrier,MINUTE
from train_v15 import timestamp


def rows(start,n,growth=0):
    return [dict(timestamp=start+i*MINUTE,open=str(100*math.exp(growth*i))) for i in range(n)]


class CostOpportunityTests(unittest.TestCase):
    def test_flat_prices_pay_exact_assumed_costs(self):
        start=timestamp('2026-03-01')
        result=audit(rows(start,180),start,start+180*MINUTE)
        self.assertEqual(result['paired_observations'],2)
        fee=.001;impact=.0003
        expected=((1-fee)*(1-impact)/((1+fee)*(1+impact))-1)*10000
        for h in ('15','60'):
            m=result['horizons'][h]
            self.assertEqual(m['moves_above_cost'],0)
            self.assertAlmostEqual(m['mean_long_return_after_assumed_cost_bps'],expected,places=9)

    def test_paired_horizons_use_delayed_entry_and_fixed_grid(self):
        start=timestamp('2026-03-01')
        data=rows(start,180,growth=.0001)
        data[0]['open']='100000' # Decision open is not entry price.
        result=audit(data,start,start+180*MINUTE)
        self.assertAlmostEqual(result['horizons']['15']['mean_reference_log_bps'],15,places=8)
        self.assertAlmostEqual(result['horizons']['60']['mean_reference_log_bps'],60,places=8)
        self.assertEqual(result['horizons']['15']['moves_above_cost'],0)
        self.assertEqual(result['horizons']['60']['moves_above_cost'],2)
        self.assertAlmostEqual(barrier(),26.000006846671294,places=8)

    def test_month_boundary_purges_both_horizons(self):
        start=timestamp('2026-03-31')+22*60*MINUTE
        result=audit(rows(start,240),start,start+240*MINUTE)
        self.assertEqual(result['month_boundary_anchors_purged'],1)
        self.assertEqual(result['paired_observations'],2)
        self.assertEqual(set(result['monthly']),{'2026-03','2026-04'})

    def test_gaps_incomplete_coverage_and_reserved_rows_rejected(self):
        start=timestamp('2026-03-01'); data=rows(start,180)
        for broken in (data[1:],data[:-1],data[:30]+data[31:],data+rows(start+180*MINUTE,1)):
            with self.assertRaises(ValueError):audit(broken,start,start+180*MINUTE)
