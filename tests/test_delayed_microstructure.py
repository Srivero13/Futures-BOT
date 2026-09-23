import math
import unittest
from build_delayed_microstructure import Sampler


class DelayedSamplerTests(unittest.TestCase):
    def feed(self,s,t,mid=100,quantity=3):
        s.accept({'receipt_monotonic_ns':round(t*1e9),'receipt_wall_ns':round(t*1e9),'session':1},(mid-1,mid+1,quantity,1))

    def test_entry_target_and_decision_features(self):
        s=Sampler()
        for i in range(25):self.feed(s,i*.5,100+i,3+i)
        self.assertEqual(len(s.rows),2)
        r=s.rows[0]
        self.assertEqual(r['decision_monotonic_ns'],1_000_000_000)
        self.assertEqual(r['entry_monotonic_ns'],1_500_000_000)
        self.assertEqual(r['label_end_monotonic_ns'],6_500_000_000)
        self.assertEqual(r['quantity_imbalance'],4/6)
        self.assertAlmostEqual(r['target_quote_return_log_bps'],math.log(112/104)*10000)
        self.assertEqual(s.rows[1]['decision_monotonic_ns'],r['label_end_monotonic_ns'])

    def test_late_entry_and_boundary(self):
        s=Sampler()
        for t in (0,.5,1,1.8):self.feed(s,t)
        self.assertEqual(s.counts['discarded_late_entry'],1)
        self.feed(s,2.3)
        s.accept({},None)
        self.assertEqual(s.rows,[])
        self.assertEqual(s.counts['discarded_boundary_or_uncovered'],1)

    def test_late_exit_and_gap(self):
        s=Sampler()
        for t in (0,.5,1,1.5,2,3,4,5,6,6.8):self.feed(s,t)
        self.assertEqual(s.counts['discarded_late_label'],1)
        self.feed(s,9)
        self.assertEqual(s.counts['discarded_receipt_gap'],1)
        self.assertEqual(s.rows,[])

    def test_flat_prices_pay_spread(self):
        s=Sampler()
        for i in range(14):self.feed(s,i*.5)
        self.assertAlmostEqual(s.rows[0]['target_quote_return_log_bps'],math.log(99/101)*10000)

    def test_verified_capture_to_dataset_and_corruption_rejection(self):
        import json
        from pathlib import Path
        import tempfile
        from unittest.mock import patch
        from record_market import Writer
        from build_delayed_microstructure import run
        with tempfile.TemporaryDirectory() as d,patch('builtins.print'):
            root=Path(d)/'capture';root.mkdir();w=Writer(root,1024**2,reserve=0)
            w.write({'kind':'session_start','session':1,'receipt_monotonic_ns':0})
            w.write({'kind':'snapshot','session':1,'receipt_monotonic_ns':1,'data':{'lastUpdateId':100,'bids':[['99','3']],'asks':[['101','1']]}})
            for i in range(200):
                w.write({'kind':'depthUpdate','session':1,'receipt_monotonic_ns':1_000_000_000+i*100_000_000,
                    'receipt_wall_ns':1_000_000_000+i*100_000_000,'sequence_status':'linked',
                    'data':{'e':'depthUpdate','s':'ETHUSDT','U':101+i,'u':101+i,'b':[],'a':[]}})
            w.close_part()
            (root/'protocol.json').write_text(json.dumps({'symbol':'ETHUSDT'}))
            (root/'summary.json').write_text(json.dumps({'parts':w.parts,'event_bytes':w.total,'counts':{'snapshots':1,'depth_linked':200}}))
            out=Path(d)/'samples';summary=run(root,out)
            self.assertEqual(summary['samples'],3)
            self.assertGreater(summary['zero_rmse_log_bps'],0)
            self.assertTrue((out/'summary.json').exists())
            part=root/w.parts[0]['file'];part.write_bytes(part.read_bytes()+b'x')
            bad=Path(d)/'bad'
            with self.assertRaises(ValueError):run(root,bad)
            self.assertFalse((bad/'samples.jsonl').exists())
            self.assertFalse((bad/'summary.json').exists())
