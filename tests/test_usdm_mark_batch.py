from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlparse,parse_qs
from download_usdm_marks import download
from download_usdm_funding import timestamp
from engine_v1.dataset import sha256
from batch_usdm_marks import audit_marks,run


class MarkBatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.first=self.root/'first'
        self.day=date(2026,8,1);start=timestamp(self.day)
        def fetch(url,path,limit):
            cursor=int(parse_qs(urlparse(url).query)['startTime'][0])
            rows=[[t,'100','102','99','101','0',t+59999,'0',0,'0','0','0'] for t in range(cursor,min(cursor+60000000,start+86400000),60000)]
            path.write_text(json.dumps(rows))
        with patch('download_usdm_marks.fetch_file',side_effect=fetch):
            download('ETHUSDT',self.day,date(2026,9,1),self.first)

    def test_saved_audit_and_rehashed_corruption(self):
        self.assertEqual(audit_marks(self.first,self.day)['rows'],1440)
        p=self.first/'marks.json';r=json.loads(p.read_text());r[0]['close']='100'
        p.write_text(json.dumps(r));s=self.first/'summary.json';m=json.loads(s.read_text())
        m['marks_sha256']=sha256(p);s.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError,'conversion'):
            audit_marks(self.first,self.day)

    def test_first_day_reused_and_six_downloads(self):
        def audited(root,day):
            return dict(approved=False,rows=1440,date=str(day),inputs_sha256={})
        with patch('batch_usdm_marks.audit_marks',side_effect=audited),patch('batch_usdm_marks.download') as d:
            r=run(self.first,self.root/'out')
            self.assertEqual(d.call_count,6);self.assertEqual(r['minutes'],10080)
            self.assertEqual(r['status'],'complete')

    def test_download_failure_preserves_first_verified_day(self):
        with patch('batch_usdm_marks.download',side_effect=OSError('offline')):
            with self.assertRaises(OSError):
                run(self.first,self.root/'out')
        r=json.loads((self.root/'out/status.json').read_text())
        self.assertEqual(r['status'],'failed');self.assertEqual(len(r['completed_days']),1)

    def test_wrong_day_and_manifest_path_rejected(self):
        with self.assertRaises(ValueError):
            audit_marks(self.first,date(2026,8,2))
        s=self.first/'summary.json';m=json.loads(s.read_text());m['pages'][0]['file']='../elsewhere'
        s.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError,'pagination'):
            audit_marks(self.first,self.day)
