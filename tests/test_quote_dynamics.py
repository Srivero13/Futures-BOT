import json
import math
from pathlib import Path
import tempfile
import unittest
from build_quote_dynamics import Sampler,DYNAMIC_FEATURES
from research_quote_dynamics import compare
from engine_v1.dataset import sha256


class DynamicsTests(unittest.TestCase):
    def feed(self,s,t,mid):
        s.accept({'receipt_monotonic_ns':round(t*1e9),'receipt_wall_ns':round(t*1e9)+1,'session':1},(mid-1,mid+1,3,1))

    def test_decision_features_do_not_use_future_quotes(self):
        s=Sampler()
        for i in range(13):self.feed(s,i*.5,100+i)
        self.assertEqual(s.pending['decision_monotonic_ns'],6_000_000_000)
        expected=math.log(112/110)*10000
        self.assertAlmostEqual(s.pending['mid_return_1s'],expected)
        self.assertAlmostEqual(s.pending['mid_return_5s'],math.log(112/102)*10000)
        for i in range(13,24):self.feed(s,i*.5,200+i)
        self.assertEqual(len(s.rows),1)
        self.assertAlmostEqual(s.rows[0]['mid_return_1s'],expected)
        self.assertEqual(s.rows[0]['imbalance_change_1s'],0)

    def test_boundary_and_gap_clear_history(self):
        s=Sampler()
        for i in range(13):self.feed(s,i*.5,100)
        s.accept({},None)
        self.assertFalse(s.history);self.assertIsNone(s.pending)
        self.feed(s,7,100);self.feed(s,9,100)
        self.assertEqual(len(s.history),1)
        self.assertIsNone(s.pending)

    def test_paired_comparison_and_reject_same_capture(self):
        from test_delayed_training import DelayedTrainingTests
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);train=root/'train';test=root/'test';fixture=DelayedTrainingTests()
            fixture.dataset(train,10**15,'capture-a');fixture.dataset(test,2*10**15,'capture-b')
            for folder in (train,test):
                samples=folder/'samples.jsonl';rows=[json.loads(line) for line in samples.read_text().splitlines()]
                for row in rows:row.update({key:0 for key in DYNAMIC_FEATURES})
                samples.write_text(''.join(json.dumps(row)+'\n' for row in rows))
                manifest=folder/'summary.json';report=json.loads(manifest.read_text())
                report['summary']['feature_set']='best_quote_dynamics_v1';report['samples_sha256']=sha256(samples)
                manifest.write_text(json.dumps(report))
            result=compare(train,test,root/'report.json')
            self.assertEqual(result['evaluation_samples'],200)
            self.assertAlmostEqual(result['dynamic_minus_base_rmse_log_bps'],0)
            with self.assertRaises(ValueError):compare(train,train,root/'bad.json')
