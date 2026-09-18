import csv
import tempfile
from pathlib import Path
import unittest
import numpy as np
from evaluate_tradeflow import flow_features, fit_predict


class FlowResearchTests(unittest.TestCase):
    def test_availability_gap_and_future_isolation(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'flow.csv'
            rows=[dict(timestamp=i*60,available_at_ms=(i+1)*60000,taker_buy_quote=2,
                       taker_sell_quote=1,agg_events=10) for i in range(45)]
            def write():
                with path.open('w') as f:
                    w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
            write();first=flow_features([path])
            self.assertNotIn(19*60000,first)
            np.testing.assert_allclose(first[20*60000],[1/3,1/3,1])
            rows[20]['taker_buy_quote']=10000;write();second=flow_features([path])
            np.testing.assert_array_equal(first[20*60000],second[20*60000])
            self.assertNotEqual(first[21*60000][0],second[21*60000][0])
            del rows[20];write();gapped=flow_features([path])
            self.assertNotIn(40*60000,gapped);self.assertIn(41*60000,gapped)
            rows[-1]['available_at_ms']=0;write()
            with self.assertRaises(ValueError):flow_features([path])

    def test_fit_uses_training_only_and_handles_constant_columns(self):
        rng=np.random.default_rng(12); x=rng.normal(size=(200,3));x[:,2]=1
        y=3*x[:,0]-2*x[:,1]+4
        target=x[:20]
        original=fit_predict(x,y,[target])[0]
        changed=fit_predict(x,y,[target,np.ones((30,3))*1e8])[0]
        np.testing.assert_array_equal(original,changed)
        self.assertLess(np.sqrt(np.mean((original-y[:20])**2)),.3)
        self.assertTrue(np.isfinite(original).all())

    def test_paired_split_purging_and_reserved_boundary(self):
        import argparse
        import json
        from unittest.mock import patch
        from evaluate_tradeflow import run
        from train_v15 import timestamp
        from engine_v1.dataset import sha256
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); flow=root/'sample-flow.csv'; flow.write_text('fixture')
            candle=root/'candles.csv';candle.write_text('fixture')
            audit=root/'audit.json'
            start=timestamp('2026-06-01');end=timestamp('2026-09-01')
            from datetime import datetime, timezone
            days={datetime.fromtimestamp(t/1000,timezone.utc).strftime('%Y-%m-%d'):{} for t in range(start,end,86400000)}
            audit.write_text(json.dumps({'summary':{'alignment_passed':True},'spec':{'symbol':'ETHUSDT',
                'input_sha256':{str(flow):sha256(flow),str(candle):sha256(candle)}},'days':days}))
            rng=np.random.default_rng(1);rows=[];features={}
            for month in ('2026-06-01','2026-07-01','2026-08-01'):
                t0=timestamp(month)
                for i in range(120):
                    t=t0+(i+2)*900000;x=rng.normal(size=6)
                    rows.append([t,t+900000,*x,float(x[0])]);features[t]=[.1,.2,1]
            # Crossing June/July label must not enter either split.
            rows.append([timestamp('2026-07-01')-900000,timestamp('2026-07-01'),*([0]*6),999])
            a=argparse.Namespace(output=root/'result.json',start='2026-06-01',reserve_from='2026-09-01',symbol='ETHUSDT',audits=[audit])
            with patch('evaluate_tradeflow.examples',return_value=iter([np.asarray(rows)])),patch('evaluate_tradeflow.flow_features',return_value=features),patch('sys.stdout'):
                summary=run(a)
            self.assertEqual(summary['paired_rows'],{'train':120,'calibration':120,'test':120})
            self.assertFalse(json.loads(a.output.read_text())['approved'])
            a.output=root/'other.json';a.reserve_from='2026-08-01'
            with self.assertRaisesRegex(ValueError,'reserved'):run(a)
            a.reserve_from='2026-09-01';flow.write_text('corrupt')
            with patch('sys.stdout'),self.assertRaisesRegex(ValueError,'changed'):run(a)
