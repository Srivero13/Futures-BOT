import unittest
import math
from build_aggressive_flow import FlowCursor,Sampler,FLOW_FEATURES
from research_aggressive_flow import compare
import json
from pathlib import Path
import tempfile
from engine_v1.dataset import sha256


def trade(i,t,m=False):
    return {'kind':'aggTrade','session':1,'receipt_monotonic_ns':round(t*1e9),
            'data':{'a':i,'p':'100','q':'1','m':m}}


def quote(i,t):
    return {'kind':'depthUpdate','session':1,'receipt_monotonic_ns':round(t*1e9),
            'receipt_wall_ns':round(t*1e9)+1,'marker':i}


class AggressiveFlowTests(unittest.TestCase):
    def test_receipt_ties_exclude_future_and_maker_direction(self):
        first=quote(1,1);second=quote(2,1.5)
        cursor=FlowCursor([trade(1,1,False),first,trade(2,1,True),second])
        cursor.advance(first)
        self.assertEqual(cursor.features(10**9,.5)[0:2],[1,1])
        cursor.advance(first)  # repeated callback cannot consume future trades
        self.assertEqual(len(cursor.events),1)
        cursor.advance(second)
        self.assertEqual(cursor.features(15*10**8,.5)[0:2],[0,0])
        self.assertEqual(cursor.features(7*10**9,.5),[0,0,0,0])

    def test_trade_id_gap_and_invalid_flag(self):
        q=quote(1,1)
        c=FlowCursor([trade(1,0),trade(3,.5,True),q]);c.advance(q)
        self.assertEqual(c.generation,1);self.assertEqual(c.features(10**9,.5)[1],-1)
        bad=trade(1,0);bad['data']['m']='false'
        with self.assertRaises(ValueError):FlowCursor([bad,q]).advance(q)

    def test_sample_features_frozen_before_future_sells(self):
        events=[];quotes=[]
        for i in range(24):
            q=quote(i,i*.5);quotes.append(q)
            events.extend([trade(i,i*.5,i>12),q])
        cursor=FlowCursor(events);s=Sampler(cursor)
        for q in quotes:s.accept(q,(99,101,3,1))
        self.assertEqual(len(s.rows),1)
        self.assertEqual(s.rows[0]['decision_monotonic_ns'],6_000_000_000)
        self.assertEqual(s.rows[0]['taker_imbalance_5s'],1)
        self.assertEqual(s.rows[0]['flow_book_interaction'],.5)
        self.assertAlmostEqual(s.rows[0]['log_agg_rate_5s'],math.log1p(2))
        cursor.finish()

    def test_second_reader_rejects_corruption(self):
        import tempfile,json
        from pathlib import Path
        from build_aggressive_flow import records
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'events-00000.jsonl').write_text(json.dumps(trade(1,0))+'\n')
            (root/'summary.json').write_text(json.dumps({'parts':[{'file':'events-00000.jsonl','bytes':1,'sha256':'bad'}]}))
            with self.assertRaises(ValueError):list(records(root))

    def test_paired_comparison_and_reject_same_capture(self):
        from test_delayed_training import DelayedTrainingTests
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);train=root/'train';test=root/'test';fixture=DelayedTrainingTests()
            fixture.dataset(train,10**15,'capture-a');fixture.dataset(test,2*10**15,'capture-b')
            for folder in (train,test):
                samples=folder/'samples.jsonl';rows=[json.loads(line) for line in samples.read_text().splitlines()]
                for row in rows:row.update({key:0 for key in FLOW_FEATURES})
                samples.write_text(''.join(json.dumps(row)+'\n' for row in rows))
                manifest=folder/'summary.json';report=json.loads(manifest.read_text())
                report['summary']['feature_set']='aggressive_flow_v1';report['samples_sha256']=sha256(samples)
                manifest.write_text(json.dumps(report))
            result=compare(train,test,root/'report.json')
            self.assertEqual(result['evaluation_samples'],200)
            self.assertAlmostEqual(result['flow_minus_base_rmse_log_bps'],0)
            with self.assertRaises(ValueError):compare(train,train,root/'bad.json')
