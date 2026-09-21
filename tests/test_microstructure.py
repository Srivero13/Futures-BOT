import unittest
from build_microstructure import Sampler


class MicrostructureTests(unittest.TestCase):
    def feed(self,s,t,mid=100):
        s.accept({'receipt_monotonic_ns':int(t*1e9),'receipt_wall_ns':int(t*1e9),'session':1},(mid-1,mid+1,3,1))

    def test_fixed_horizon_features_and_nonoverlap(self):
        s=Sampler()
        for i in range(25):self.feed(s,i*.5,100+i*.1)
        self.assertEqual(len(s.rows),2)
        self.assertEqual(s.rows[0]['decision_monotonic_ns'],1_000_000_000)
        self.assertEqual(s.rows[0]['label_end_monotonic_ns'],s.rows[1]['decision_monotonic_ns'])
        self.assertEqual(s.rows[0]['mid'],100.2)
        self.assertEqual(s.rows[0]['quantity_imbalance'],.5)
        self.assertGreater(s.rows[0]['target_mid_return_log_bps'],0)

    def test_boundary_and_gap_drop_pending_labels(self):
        s=Sampler()
        for i in range(8):self.feed(s,i*.5)
        s.accept({},None)
        for i in range(8,16):self.feed(s,i*.5)
        self.feed(s,20)
        self.assertEqual(s.rows,[])
        self.assertEqual(s.counts['discarded_boundary_or_uncovered'],1)
        self.assertEqual(s.counts['discarded_receipt_gap'],1)

    def test_late_target_is_not_accepted(self):
        s=Sampler()
        for i in range(6):self.feed(s,i)
        self.feed(s,5.5);self.feed(s,6.4)
        self.assertEqual(s.rows,[])
        self.assertEqual(s.counts['discarded_late_label'],1)

    def test_verified_capture_to_dataset_and_corruption_rejection(self):
        import json
        from pathlib import Path
        import tempfile
        from unittest.mock import patch
        from record_market import Writer
        from build_microstructure import run
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
            self.assertEqual(summary['zero_rmse_log_bps'],0)
            self.assertTrue((out/'summary.json').exists())
            part=root/w.parts[0]['file'];part.write_bytes(part.read_bytes()+b'x')
            bad=Path(d)/'bad'
            with self.assertRaises(ValueError):run(root,bad)
            self.assertFalse((bad/'samples.jsonl').exists())
            self.assertFalse((bad/'summary.json').exists())
