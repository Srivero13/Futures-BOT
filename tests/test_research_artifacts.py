import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from engine_v1.research_artifacts import validate_report
import parallel_research
import engine_v1.research_mlp


def fixture(path, month=5, backend='polynomial', audits=None):
    protocol = dict(symbol='ETHUSDT', start=f'2026-{month-2:02d}-01',
                    reserve_from='2026-09-01', backend=backend, horizon_minutes=15,
                    alpha=10, input_sha256=audits or {})
    for key, m in [('train_end_ms',month-1),('calibration_end_ms',month),('test_end_ms',month+1)]:
        protocol[key]=int(datetime(2026,m,1,tzinfo=timezone.utc).timestamp()*1000)
    rankings={name:dict(rmse_log_bps=value,spearman=None,zero_rmse_log_bps_same_rows=2,
                       buckets=[dict(count=100)]) for name,value in
              [('candles_only',1),('candles_plus_flow',1.5)]}
    report=dict(approved=False,pnl=None,protocol=protocol,rankings=rankings,
        summary=dict(paired_rows=dict(train=100,calibration=100,test=100),
                     test_rmse_log_bps={k:v['rmse_log_bps'] for k,v in rankings.items()},
                     test_spearman={k:None for k in rankings},
                     zero_rmse_log_bps=2,flow_minus_candle_rmse_log_bps=.5))
    path.write_text(json.dumps(report))
    path.with_suffix('.protocol.json').write_text(json.dumps(protocol))
    return report


class ArtifactTests(unittest.TestCase):
    def test_validation_rejects_missing_mismatched_and_nonfinite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'report.json'
            with self.assertRaises(OSError): validate_report(path,5,'polynomial',{})
            for mutation in ('backend','nan','count','difference','approved','audit'):
                r=fixture(path)
                if mutation=='backend': r['protocol']['backend']='cuda-mlp'
                elif mutation=='nan': r['summary']['zero_rmse_log_bps']=float('nan')
                elif mutation=='count': r['rankings']['candles_only']['buckets'][0]['count']=99
                elif mutation=='difference': r['summary']['flow_minus_candle_rmse_log_bps']=0
                elif mutation=='approved': r['approved']=True
                path.write_text(json.dumps(r))
                audits={'expected':'sha'} if mutation=='audit' else {}
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    validate_report(path,5,'polynomial',audits)
            fixture(path)
            self.assertEqual(validate_report(path,5,'polynomial',{})['month'],5)

    def run_batch(self, tmp, missing=False):
        root=Path(tmp); audit=root/'audits'; audit.mkdir()
        for month in range(3,9):
            (audit/f'ETHUSDT-2026-{month:02d}-alignment.json').write_text('{}')
        output=root/'out'
        def worker(jobs,*args,**kwargs):
            for job in jobs:
                argv=job['argv']; dest=Path(argv[-1])
                if missing: continue
                month=int(dest.name[:2])
                audits={str((audit/f'ETHUSDT-2026-{m:02d}-alignment.json').resolve()):
                        parallel_research.read_json(audit/f'ETHUSDT-2026-{m:02d}-alignment.json')[1]
                        for m in range(month-2,month+1)}
                fixture(dest,month,job['name'],audits)
        torch=SimpleNamespace(__version__='test',version=SimpleNamespace(cuda='test'),
                              cuda=SimpleNamespace(get_device_name=lambda _: 'test'))
        with patch.dict('sys.modules',{'torch':torch}), patch(
                'engine_v1.research_mlp.fit_predict'), patch(
                'parallel_research.run_workers',side_effect=worker) as workers, patch(
                'sys.argv',['parallel_research.py','--audit-dir',str(audit),'--output-dir',str(output)]):
            if missing:
                with self.assertRaises(OSError): parallel_research.main()
                self.assertEqual(workers.call_count,1)
            else: parallel_research.main()
        return json.loads((output/'batch-status.json').read_text())

    def test_zero_exit_missing_report_fails_before_next_month(self):
        with tempfile.TemporaryDirectory() as tmp:
            status=self.run_batch(tmp,missing=True)
            self.assertEqual(status['state'],'failed')
            self.assertEqual(status['verified_reports'],[])

    def test_eight_verified_reports_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            status=self.run_batch(tmp)
            self.assertEqual(status['state'],'completed')
            self.assertEqual(len(status['verified_reports']),8)
            self.assertFalse(status['approved'])
            self.assertTrue(all(len(x['sha256'])==64 for x in status['verified_reports']))
