import math
import unittest
from profile_delayed_horizons import Sampler,summarize,HORIZONS


class HorizonProfileTests(unittest.TestCase):
    def sampler(self,score=1):
        return Sampler({'frozen_at_wall_ns':0,'training_forecast_bucket_cuts':[.1],
            'mean':[0,0,0],'scale':[1,1,1],'coefficients':[score,0,0,0]})

    def feed(self,s,t,mid=100):
        s.accept({'receipt_monotonic_ns':round(t*1e9),'receipt_wall_ns':round(t*1e9)+1,'session':1},(mid-1,mid+1,3,1))

    def test_paired_entries_and_nonoverlapping_anchors(self):
        s=self.sampler()
        for i in range(245):self.feed(s,i*.5,100+i*.1)
        self.assertEqual(len(s.rows),2)
        row=s.rows[0]
        self.assertEqual(row['entry_ns'],1_500_000_000)
        self.assertEqual(row['entry_ask'],101.3)
        for h in HORIZONS:
            target=row['targets'][str(h)]
            self.assertEqual(target['end_ns']-row['entry_ns'],h*1_000_000_000)
            self.assertAlmostEqual(target['quote_return_log_bps'],math.log(target['exit_bid']/101.3)*10000)
        self.assertEqual(s.rows[1]['decision_ns'],row['targets']['60']['end_ns'])
        report=summarize(s)
        self.assertEqual([x['selected_samples'] for x in report['horizons'].values()],[2]*4)

    def test_boundary_discards_short_horizons_too(self):
        s=self.sampler()
        for i in range(70):self.feed(s,i*.5)
        self.assertEqual(len(s.pending['targets']),3)
        s.accept({},None)
        self.assertEqual(s.rows,[])
        self.assertEqual(s.counts['discarded_boundary_or_uncovered'],1)

    def test_late_label_gap_and_freeze(self):
        s=self.sampler()
        for t in (0,.5,1,1.5,2,3,4,5,6,6.8):self.feed(s,t)
        self.assertEqual(s.counts['discarded_late_label'],1)
        self.feed(s,9)
        self.assertEqual(s.counts['discarded_receipt_gap'],1)
        with self.assertRaises(ValueError):self.feed(s,-1)

    def test_empty_selection_is_null(self):
        s=self.sampler(-1)
        for i in range(124):self.feed(s,i*.5)
        report=summarize(s)
        self.assertEqual(report['selected_samples'],0)
        self.assertTrue(all(x['selected_mean_quote_return_log_bps'] is None for x in report['horizons'].values()))
