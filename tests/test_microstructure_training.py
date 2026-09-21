import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from engine_v1.dataset import sha256
from train_microstructure import SETTINGS,fit,evaluate,fit_arrays,predict


class MicrostructureTrainingTests(unittest.TestCase):
    def dataset(self,path,start,capture):
        path.mkdir();rng=np.random.default_rng(27);rows=[]
        for i in range(200):
            imbalance=float(rng.uniform(-1,1))
            rows.append(dict(decision_monotonic_ns=i*6_000_000_000,label_end_monotonic_ns=i*6_000_000_000+5_000_000_000,
                decision_wall_ns=start+i*6_000_000_000,spread_bps=1.,quantity_imbalance=imbalance,log_best_quantity=2.,target_mid_return_log_bps=imbalance*2))
        samples=path/'samples.jsonl';samples.write_text(''.join(json.dumps(r)+'\n' for r in rows))
        verify=path/'replay-verification.json';verify.write_text('{"integrity_passed":true}')
        (path/'summary.json').write_text(json.dumps({'summary':dict(SETTINGS,samples=200),'samples_sha256':sha256(samples),
            'replay_sha256':sha256(verify),'capture':capture,'code_sha256':{'fixture':'fixed'}}))

    def test_frozen_fit_later_evaluation_and_rejections(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);train=root/'train';test=root/'test';early=root/'early'
            self.dataset(train,10**15,'capture-a');self.dataset(test,2*10**15,'capture-b');self.dataset(early,0,'capture-c')
            model=root/'model.json'
            with patch('train_microstructure.time.time_ns',return_value=15*10**14):fit(train,model)
            before=sha256(model)
            s=evaluate(test,model,root/'evaluation.json')
            self.assertLess(s['model_rmse_log_bps'],s['zero_rmse_log_bps']*.1)
            self.assertEqual(sha256(model),before)
            with self.assertRaises(ValueError):evaluate(train,model,root/'same.json')
            with self.assertRaises(ValueError):evaluate(early,model,root/'early.json')
            with self.assertRaises(ValueError):fit(train,model)
            (test/'samples.jsonl').write_text('tamper')
            with self.assertRaisesRegex(ValueError,'checksum'):evaluate(test,model,root/'tamper.json')
