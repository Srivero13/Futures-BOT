from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from audit_usdm_funding import audit, grid_diagnostic
from download_usdm_funding import download, timestamp
from engine_v1.dataset import sha256


class FundingAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'funding'
        self.start,self.end,self.reserve=date(2026,8,1),date(2026,8,8),date(2026,9,1)
        self.rows=[dict(symbol='ETHUSDT',fundingTime=timestamp(self.start)+i*28800000+i%5,
                        fundingRate='0.0001',markPrice='2500') for i in range(21)]
        def fetch(url,path,limit):
            path.write_text(json.dumps(self.rows))
        with patch('download_usdm_funding.fetch_file',side_effect=fetch):
            download('ETHUSDT',self.start,self.end,self.reserve,self.root)

    def run_audit(self):
        return audit(self.root,'ETHUSDT',self.start,self.end,self.reserve)

    def test_jitter_matches_reference_without_mutation(self):
        before=(self.root/'funding.json').read_bytes()
        r=self.run_audit()
        self.assertTrue(r['reference_grid']['reference_grid_complete'])
        self.assertEqual(r['reference_grid']['expected_reference_slots'],21)
        self.assertEqual(r['reference_grid']['max_absolute_offset_ms'],4)
        self.assertFalse(r['schedule_coverage_verified'])
        self.assertEqual(before,(self.root/'funding.json').read_bytes())

    def test_missing_duplicate_and_offgrid_are_visible(self):
        start=timestamp(self.start)
        r=grid_diagnostic([{'funding_time_ms':start}, {'funding_time_ms':start+1},
                           {'funding_time_ms':start+28800000+1001}],start,start+86400000)
        self.assertFalse(r['reference_grid_complete'])
        self.assertEqual(r['duplicate_reference_slots_ms'],[start])
        self.assertEqual(len(r['missing_reference_slots_ms']),2)
        self.assertEqual(len(r['off_grid_events_ms']),1)

    def test_rehashed_conversion_tampering_rejected(self):
        p=self.root/'funding.json'
        r=json.loads(p.read_text());r[0]['funding_rate']='0.5'
        p.write_text(json.dumps(r))
        s=self.root/'summary.json';m=json.loads(s.read_text())
        m['funding_sha256']=sha256(p);s.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError,'differs from raw'):
            self.run_audit()

    def test_raw_corruption_and_metadata_rejected(self):
        with self.assertRaises(ValueError):
            audit(self.root,'BTCUSDT',self.start,self.end,self.reserve)
        p=self.root/'page-00.json';p.write_text('[]')
        with self.assertRaisesRegex(ValueError,'integrity mismatch'):
            self.run_audit()
