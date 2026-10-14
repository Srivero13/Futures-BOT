import json
from pathlib import Path
import tempfile
import unittest
from record_basis_quotes import quote,pair
from audit_basis_quotes import audit
from engine_v1.dataset import sha256


class BasisAuditTests(unittest.TestCase):
    def fixture(self,root,mutation=None):
        raw=json.dumps(dict(s='ETHUSDT',u=1,b='100',a='101',B='2',A='2',e='bookTicker'))
        spot=quote(raw,'spot','ETHUSDT',1000000000,1)
        future=quote(raw,'usdm','ETHUSDT',1100000000,2)
        paired=pair(dict(spot=spot,usdm=future),1200000000)
        if mutation=='age': paired['ages_ns']['spot']=0
        if mutation=='quote': paired['spot']=dict(spot,bid='99')
        if mutation=='stale': paired=pair(dict(spot=spot,usdm=future),1200000000);paired['paired_monotonic_ns']=1500000000
        rows=[spot,future,paired]
        if mutation=='duplicate': rows.append(paired)
        f=root/'events-00000.jsonl'
        f.write_text(''.join(json.dumps(r)+'\n' for r in rows))
        summary=dict(approved=False,observe_only=True,capture_completed=True,stop_reason='duration',
            workers_stopped=True,errors=[],event_bytes=f.stat().st_size,
            parts=[dict(file=f.name,bytes=f.stat().st_size,sha256=sha256(f))],
            counts=dict(spot_quotes=1,usdm_quotes=1,receipt_pairs=1,unpaired_updates=1))
        if mutation=='count': summary['counts']['receipt_pairs']=2
        if mutation=='path': summary['parts'][0]['file']='../events-00000.jsonl'
        (root/'summary.json').write_text(json.dumps(summary))
        (root/'protocol.json').write_text(json.dumps(dict(approved=False,observe_only=True,
            symbol='ETHUSDT',max_receipt_age_ms=250,max_mib=1)))
        if mutation=='hash': f.write_text(f.read_text()+'\n')

    def test_replays_saved_pairs_and_timing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root);r=audit(root)
            self.assertTrue(r['pair_replay_passed']);self.assertFalse(r['approved'])
            self.assertEqual(r['receipt_timing_ms']['spot_age']['mean'],200)
            self.assertEqual(r['receipt_timing_ms']['skew']['max'],100)

    def test_tampering_and_inconsistent_rehashed_records_fail(self):
        for case in ('hash','age','quote','stale','duplicate','count','path'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);self.fixture(root,case)
                with self.assertRaises(ValueError): audit(root)
