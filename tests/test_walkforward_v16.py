import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from engine_v1.dataset import sha256
from engine_v1.model import RidgeModel
from train_v15 import timestamp
from walkforward_v16 import folds, average_ranks, ranking, collect, run


class WalkForwardTests(unittest.TestCase):
    def test_schedule_crosses_year_and_nonoverlap(self):
        plan=folds('2026-01-01',3)
        self.assertEqual(plan[0]['train_end'],'2025-12-01')
        self.assertEqual(plan[0]['test_end'],plan[1]['calibration_end'])
        self.assertEqual(plan[-1]['test_end'],'2026-04-01')
        for first,months in [('2026-01-02',2),('2026-01-01',0),('2026-01-01',25)]:
            with self.assertRaises(ValueError):
                folds(first,months)

    def test_tied_ranks(self):
        np.testing.assert_array_equal(average_ranks(np.array([3.,1.,1.,2.])),[4,1.5,1.5,3])

    def test_known_positive_and_negative_rank(self):
        x=np.arange(100,dtype=float)
        calibration=np.column_stack((x,x))
        for sign in (1,-1):
            r=ranking(calibration,np.column_stack((x,sign*x)))
            self.assertAlmostEqual(r['spearman'],sign)
            self.assertEqual(np.sign(r['top_minus_bottom_actual_log_bps']),sign)
            self.assertEqual(sum(b['count'] for b in r['buckets']),100)

    def test_test_data_cannot_change_calibration_cuts(self):
        x=np.arange(100,dtype=float)
        cal=np.column_stack((x,x))
        a=ranking(cal,cal)
        b=ranking(cal,np.column_stack((x*100,-x*100)))
        self.assertEqual(a['calibration_forecast_cuts_log_bps'],b['calibration_forecast_cuts_log_bps'])

    def test_constant_and_empty_buckets(self):
        x=np.arange(100,dtype=float)
        r=ranking(np.column_stack((np.ones(100),x)),np.column_stack((np.ones(100),x)))
        self.assertIsNone(r['spearman'])
        self.assertIsNone(r['top_minus_bottom_actual_log_bps'])
        self.assertEqual(len(r['buckets']),1)
        r=ranking(np.column_stack((x,x)),np.column_stack((x+1000,x)))
        self.assertIsNone(r['top_minus_bottom_actual_log_bps'])
        self.assertIsNone(r['buckets'][0]['mean_actual_log_bps'])

    def test_grid_and_label_end_purge(self):
        m=RidgeModel('ETHUSDT',3,[0]*6,[1]*6,[0]*6,0,0,0,0,100,30,1,1)
        b=np.array([[i*60000,(i+3)*60000,0,0,0,0,0,0,1] for i in range(1,13)],dtype=float)
        data,counts=collect(lambda:iter([b]),m,60000,12*60000)
        self.assertEqual(counts['grid_examples'],2)  # decisions 3,6; 9 ends at excluded boundary
        self.assertEqual(len(data),2)
        with patch('walkforward_v16.MAX_RANK_ROWS',1):
            with self.assertRaises(ValueError):
                collect(lambda:iter([b]),m,60000,12*60000)

    def test_insufficient_and_nonfinite_fail(self):
        with self.assertRaises(ValueError):
            ranking(np.zeros((29,2)),np.zeros((30,2)))
        with self.assertRaises(ValueError):
            ranking(np.full((30,2),np.nan),np.zeros((30,2)))

    def test_two_fold_pipeline_and_resume_preserves_models(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root)
            paths=[]
            for month in range(1,5):
                path=root/f'2024-{month:02}.csv'
                paths.append(path)
                with path.open('w') as handle:
                    writer=csv.DictWriter(handle,fieldnames=['timestamp','open','high','low','close','volume'])
                    writer.writeheader()
                    begin=timestamp(f'2024-{month:02}-01')//1000
                    for i in range(600):
                        price=100+np.sin(i/10)*.1
                        writer.writerow(dict(timestamp=begin+i*60,open=price,close=price,high=price+.01,low=price-.01,volume=100+i%5))
                path.with_suffix('.json').write_text(json.dumps(dict(sha256=sha256(path),venue='binance',symbol='ETHUSDT',timeframe_ms=60000)))
            with patch('sys.stdout'):
                report=run(paths,'ETHUSDT','2024-03-01',2,root/'models',root/'result.json')
                again=run(paths,'ETHUSDT','2024-03-01',2,root/'models',root/'second.json')
                with self.assertRaises(ValueError):
                    run(paths,'ETHUSDT','2024-03-01',2,root/'models',root/'result.json')
            self.assertEqual(report['summary']['folds'],2)
            self.assertFalse(report['approved'])
            self.assertIsNone(report['pnl'])
            self.assertEqual([f['model_sha256'] for f in report['folds']],
                             [f['model_sha256'] for f in again['folds']])
            for fold in report['folds']:
                payload=json.loads((Path(fold['model_directory'])/'model.json').read_text())['model']
                self.assertFalse(payload['approved'])
                self.assertEqual(payload['train_end_ms'],timestamp(fold['train_end']))
                self.assertEqual(payload['calibration_end_ms'],timestamp(fold['calibration_end']))
                self.assertGreaterEqual(fold['test_counts']['accepted'],30)


if __name__ == '__main__':
    unittest.main()
