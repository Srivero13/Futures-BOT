import unittest
import numpy as np
from diagnose_usdm_basis import analyze


class BasisTests(unittest.TestCase):
    def rows(self, n=121):
        return [dict(timestamp=i*60000,close='100') for i in range(n)]

    def test_identical_prices_and_common_horizon_anchors(self):
        result=analyze(self.rows(),self.rows())
        self.assertEqual(result['paired_hourly_anchors'],2)
        self.assertEqual(result['basis_log_bps']['mean'],0)
        for values in result['horizons_minutes'].values():
            self.assertEqual(values['basis_change_log_bps']['count'],2)
            self.assertIsNone(values['pearson_initial_basis_vs_change_descriptive'])
            self.assertEqual(values['strictly_closer_to_zero_count'],0)

    def test_known_basis_decay_and_equal_underlying_move(self):
        s=self.rows();f=self.rows()
        for i in range(len(s)):
            s[i]['close']=str(100*np.exp(i*.001))
            f[i]['close']=str(float(s[i]['close'])*np.exp((120-i)/10000))
        result=analyze(s,f)
        self.assertAlmostEqual(result['basis_log_bps']['mean'],60,places=8)
        for h in (15,60):
            v=result['horizons_minutes'][str(h)]
            self.assertAlmostEqual(v['basis_change_log_bps']['mean'],-h,places=8)
            self.assertEqual(v['strictly_closer_to_zero_count'],2)

    def test_bad_alignment_and_prices_fail(self):
        for case in ('missing','shift','duplicate','nan','zero','negative'):
            s=self.rows();f=self.rows()
            if case=='missing': f.pop()
            elif case=='shift': f[2]['timestamp']+=60000
            elif case=='duplicate': s[2]['timestamp']=s[1]['timestamp']
            else: f[2]['close']={'nan':'NaN','zero':'0','negative':'-1'}[case]
            with self.subTest(case=case),self.assertRaises(ValueError): analyze(s,f)
