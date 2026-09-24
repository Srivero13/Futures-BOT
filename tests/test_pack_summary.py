import copy
import math
import unittest
from summarize_feature_pack import consolidate


class PackSummaryTests(unittest.TestCase):
    def fixture(self):
        training={'capture':'train','last_label_wall_ns_estimate':5,'builder_code_sha256':{'builder':'sha'}}
        pack={'kind':'frozen_feature_pack_v1','frozen_at_wall_ns':10,'training':{k:training for k in ('flow','dynamics')},'models':{'baseline':{'top_cutoff':.4}}}
        def report(capture,start,n,rmse,selected,mean):
            p={'capture':capture,'first_decision_wall_ns':start,'last_label_wall_ns_estimate':start+10,'builder_code_sha256':{'builder':'sha'}}
            return {'pack_sha256':'pack','evaluation':{k:p for k in ('flow','dynamics')},'summary':{'counts':{'common_rows':n,'flow_rows':n,'dynamics_rows':n},'zero_rmse_log_bps':3,'models':{'baseline':{'rmse_log_bps':rmse,'selected_samples':selected,'selected_mean_quote_log_bps':mean,'cost_eligible_forecasts':0,'frozen_top_cutoff_log_bps':.4}}}}
        return pack,[report('a',20,100,1,10,2),report('b',40,300,2,30,4)]

    def test_correct_weighting(self):
        p,r=self.fixture();s,_=consolidate(p,'pack',r)
        self.assertEqual(s['common_rows'],400)
        m=s['models']['baseline'];self.assertAlmostEqual(m['pooled_rmse_log_bps'],math.sqrt(3.25))
        self.assertEqual(m['selected_weighted_mean_quote_log_bps'],3.5)
        self.assertEqual(m['captures_beating_zero'],2)

    def test_duplicate_overlap_pack_cutoff_and_counts_rejected(self):
        p,r=self.fixture()
        with self.assertRaises(ValueError):consolidate(p,'pack',[r[0],r[0]])
        for edit in ('overlap','pack','cutoff','counts'):
            reports=copy.deepcopy(r)
            if edit=='overlap':reports[1]['evaluation']['flow']['first_decision_wall_ns']=25
            if edit=='pack':reports[1]['pack_sha256']='other'
            if edit=='cutoff':reports[1]['summary']['models']['baseline']['frozen_top_cutoff_log_bps']=.3
            if edit=='counts':reports[1]['summary']['models']['baseline']['selected_samples']=301
            with self.assertRaises(ValueError):consolidate(p,'pack',reports)
