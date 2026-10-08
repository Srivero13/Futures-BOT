import json
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_usdm_pilot
from download_usdm_pilot import download
from audit_usdm_pilot import audit
from engine_v1.dataset import sha256


class UsdmAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.day, self.reserve = date(2026, 8, 1), date(2026, 9, 1)
        a, c = test_usdm_pilot.UsdmPilotTests().archive(self.root)
        def fetch(url, path, limit):
            path.write_bytes((c if url.endswith('.CHECKSUM') else a).read_bytes())
        self.pilot = self.root/'pilot'
        with patch('download_usdm_pilot.fetch_file', side_effect=fetch):
            self.meta = download('ETHUSDT', self.day, self.reserve, self.pilot)
        self.csv = next(self.pilot.glob('*.csv'))
        self.spot = self.root/'spot.csv'
        self.spot.write_bytes(self.csv.read_bytes())
        self.spotmeta = dict(self.meta, venue='binance', market='spot')
        self.spot.with_suffix('.json').write_text(json.dumps(self.spotmeta))

    def run_audit(self):
        return audit(self.pilot, self.spot, 'ETHUSDT', self.day, self.reserve)

    def test_complete_alignment_without_mutation(self):
        before = {str(p): sha256(p) for p in self.root.rglob('*') if p.is_file()}
        r = self.run_audit()
        self.assertEqual(r['matched_minutes'], 1440)
        self.assertTrue(r['archive_conversion_equal'])
        self.assertFalse(r['approved'])
        self.assertEqual(before, {str(p): sha256(p) for p in self.root.rglob('*') if p.is_file()})

    def test_rehashed_modified_conversion_rejected(self):
        self.csv.write_text(self.csv.read_text().replace('2.5', '2.6', 1))
        self.meta.update(sha256=sha256(self.csv), bytes=self.csv.stat().st_size)
        self.csv.with_suffix('.json').write_text(json.dumps(self.meta))
        with self.assertRaisesRegex(ValueError, 'differs from source'):
            self.run_audit()

    def test_missing_spot_minute_even_with_valid_hash_rejected(self):
        rows = self.spot.read_text().splitlines()
        self.spot.write_text('\n'.join(rows[:10]+rows[11:])+'\n')
        self.spotmeta['sha256'] = sha256(self.spot)
        self.spot.with_suffix('.json').write_text(json.dumps(self.spotmeta))
        with self.assertRaisesRegex(ValueError, 'missing or misaligned'):
            self.run_audit()

    def test_tampered_archive_wrong_venue_and_reserve_rejected(self):
        with self.assertRaises(ValueError):
            audit(self.pilot, self.spot, 'ETHUSDT', self.day, self.day)
        self.spotmeta['venue'] = 'binance_usdm'
        self.spot.with_suffix('.json').write_text(json.dumps(self.spotmeta))
        with self.assertRaisesRegex(ValueError, 'Provenance mismatch'):
            self.run_audit()
        archive = next(self.pilot.glob('*.zip'))
        with archive.open('ab') as f:
            f.write(b'changed')
        with self.assertRaisesRegex(ValueError, 'integrity mismatch'):
            self.run_audit()
