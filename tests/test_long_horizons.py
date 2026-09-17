import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from backtest_v16 import simulate
from engine_v1.dataset import examples, sha256, segment
from engine_v1.model import RidgeModel
from engine_v1.nonlinear import load_model
from train_v15 import timestamp
from walkforward_v16 import collect, run


def write_shard(path,start,count):
    with path.open('w') as f:
        writer=csv.DictWriter(f,fieldnames=['timestamp','open','high','low','close','volume'])
        writer.writeheader()
        for i in range(count):
            price=100+np.sin(i/10)*.1
            writer.writerow(dict(timestamp=start//1000+i*60,open=price,high=price+.01,
                                 low=price-.01,close=price,volume=100+i%5))
    path.with_suffix('.json').write_text(json.dumps(dict(sha256=sha256(path),venue='binance',
                                                        symbol='ETHUSDT',timeframe_ms=60000)))


class LongHorizonTests(unittest.TestCase):
    def test_chunk_equivalence_and_exact_labels(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'data.csv'
            write_shard(path,0,350)
            for h in (15,60):
                a=np.concatenate(list(examples([path],h,32)))
                b=np.concatenate(list(examples([path],h,128)))
                np.testing.assert_allclose(a,b,rtol=1e-10,atol=1e-10)
                self.assertTrue(np.all(a[:,1]-a[:,0]==h*60000))
                decision=int(a[0,0]//60000)
                expected=np.log((100+np.sin((decision+h)/10)*.1)/(100+np.sin(decision/10)*.1))*10000
                self.assertAlmostEqual(a[0,8],expected)
                selected=np.concatenate(list(segment(lambda:iter([a]),0,200*60000)))
                self.assertTrue(np.all(selected[:,1]<200*60000))

    def test_baselines_share_mask_and_use_only_past_momentum(self):
        m=RidgeModel('ETHUSDT',60,[0]*6,[1]*6,[0]*6,1,0,0,0,100,30,1,1)
        b=np.array([[60*60000,120*60000,0,0,.002,0,0,0,7],
                    [120*60000,180*60000,99,0,.003,0,0,0,8]],dtype=float)
        pairs,counts=collect(lambda:iter([b]),m,0,240*60000,include_baselines=True)
        self.assertEqual(counts['ood_rejected'],1)
        np.testing.assert_allclose(pairs,[[1,7,60,-60,0]])
        b[:,8]=999
        changed,_=collect(lambda:iter([b]),m,0,240*60000,include_baselines=True)
        np.testing.assert_array_equal(changed[:,[0,2,3,4]],pairs[:,[0,2,3,4]])

    def test_long_position_duration_and_model_roundtrip(self):
        with tempfile.TemporaryDirectory() as root:
            for h in (15,60):
                m=RidgeModel('ETHUSDT',h,[0]*6,[1]*6,[0]*6,100,0,0,0,100,30,1,1)
                p=Path(root)/f'model-{h}.json'; m.save(p)
                self.assertEqual(load_model(p).horizon_bars,h)
                rows=[dict(timestamp=i*60000,open='100',close='100',high='100',low='100',volume='1') for i in range(200)]
                report=simulate(rows,m,21*60000,200*60000)
                self.assertGreater(report['summary']['closed_trades'],0)
                for trade in report['trades']:
                    self.assertEqual(trade['exit_ms']-trade['entry_ms'],h*60000)

    def test_reserved_period_fails_before_training(self):
        with patch('walkforward_v16.run_training') as training:
            with self.assertRaisesRegex(ValueError,'reserved'):
                run([],'ETHUSDT','2026-08-01',2,'unused','unused.json',reserve_from='2026-09-01')
            training.assert_not_called()

    def test_long_horizon_pipeline_and_protocol_change_rejection(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root)
            paths=[]
            for month in (1,2,3):
                p=root/f'2024-{month:02}.csv'
                write_shard(p,timestamp(f'2024-{month:02}-01'),3000)
                paths.append(p)
            for h in (15,60):
                out=root/f'report-{h}.json'
                with patch('sys.stdout'):
                    report=run(paths,'ETHUSDT','2024-03-01',1,root/'models',out,horizon=h,reserve_from='2024-04-01')
                self.assertFalse(report['approved'])
                self.assertEqual(report['protocol']['reserve_from'],'2024-04-01')
                baseline=report['folds'][0]['baselines_same_model_accepted_rows']
                self.assertEqual(set(baseline),{'momentum','mean_reversion','zero'})
                self.assertAlmostEqual(baseline['zero']['rmse_log_bps'],report['folds'][0]['ranking']['zero_rmse_log_bps_same_rows'])
                plan=json.loads(out.with_suffix('.protocol.json').read_text())
                self.assertEqual(plan['horizon'],h)
                out.unlink()
                with patch('walkforward_v16.run_training') as training:
                    with self.assertRaisesRegex(ValueError,'Protocol differs'):
                        run(paths,'ETHUSDT','2024-03-01',1,root/'models',out,horizon=h,alpha=20,reserve_from='2024-04-01')
                    training.assert_not_called()


if __name__=='__main__':
    unittest.main()
