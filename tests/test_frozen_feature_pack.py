import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from frozen_feature_pack import freeze,evaluate,paired,code_hashes
from engine_v1.dataset import sha256
from build_quote_dynamics import DYNAMIC_FEATURES
from build_aggressive_flow import FLOW_FEATURES


class FrozenPackTests(unittest.TestCase):
    def datasets(self,root,start,capture):
        from test_delayed_training import DelayedTrainingTests
        for name,features,kind,builder in [('dynamics',DYNAMIC_FEATURES,'best_quote_dynamics_v1','build_quote_dynamics.py'),('flow',FLOW_FEATURES,'aggressive_flow_v1','build_aggressive_flow.py')]:
            folder=root/name;DelayedTrainingTests().dataset(folder,start,str(capture))
            path=folder/'samples.jsonl';rows=[json.loads(s) for s in path.read_text().splitlines()]
            for row in rows:row.update({k:0. for k in features})
            path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            m=folder/'summary.json';report=json.loads(m.read_text());report['samples_sha256']=sha256(path)
            report['summary']['feature_set']=kind;report['code_sha256']={builder:code_hashes()[builder]};m.write_text(json.dumps(report))

    def test_freeze_forward_evaluation_no_refit_and_earlier_rejection(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);capture=root/'train_capture';capture.mkdir();(capture/'protocol.json').write_text('{"symbol":"ETHUSDT"}')
            training=root/'training';training.mkdir();self.datasets(training,10**15,capture)
            pack=root/'pack.json'
            with patch('frozen_feature_pack.time.time_ns',return_value=15*10**14):freeze(training/'dynamics',training/'flow',pack)
            before=sha256(pack)
            new=root/'capture';new.mkdir();(new/'protocol.json').write_text('{"symbol":"ETHUSDT"}')
            first=new/'events-00000.jsonl';first.write_text('{"receipt_wall_ns":2000000000000000}\n')
            fixture=root/'fixture';fixture.mkdir();self.datasets(fixture,2*10**15,new)
            with patch('frozen_feature_pack.build_dynamics',side_effect=lambda c,o:shutil.copytree(fixture/'dynamics',o)),patch('frozen_feature_pack.build_flow',side_effect=lambda c,o:shutil.copytree(fixture/'flow',o)),patch('frozen_feature_pack.fit_arrays',side_effect=AssertionError('Must not refit')):
                result=evaluate(new,pack,root/'result')
            self.assertEqual(result['counts']['common_rows'],200);self.assertEqual(sha256(pack),before)
            self.assertEqual(len(result['models']),3)
            first.write_text('{"receipt_wall_ns":1}\n')
            with self.assertRaises(ValueError):evaluate(new,pack,root/'early')
            self.assertFalse((root/'early').exists())
            with self.assertRaises(ValueError):freeze(training/'dynamics',training/'flow',pack)

    def test_pairing_rejects_different_capture(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.datasets(root,10**15,root/'capture')
            report=root/'flow'/'summary.json';data=json.loads(report.read_text());data['capture']='different';report.write_text(json.dumps(data))
            with self.assertRaises(ValueError):paired(root/'dynamics',root/'flow')
