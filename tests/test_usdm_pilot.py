import csv
from datetime import date, datetime, timezone
import io
import tempfile
from pathlib import Path
import unittest
import zipfile
from unittest.mock import patch

from download_usdm_pilot import HEADER, download, validate_archive
from engine_v1.dataset import sha256


class UsdmPilotTests(unittest.TestCase):
    day = date(2026, 8, 1)

    def archive(self, root, header=False, change=None):
        name = 'ETHUSDT-1m-2026-08-01'
        start = int(datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp()) * 1000
        rows = [[start + i*60000, '2', '3', '1', '2.5', '10',
                 start + i*60000 + 59999, '20', '2', '5', '10', '0'] for i in range(1440)]
        if change:
            change(rows)
        text = io.StringIO()
        w = csv.writer(text)
        if header:
            w.writerow(HEADER)
        w.writerows(rows)
        archive = root / (name + '.zip')
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr(name + '.csv', text.getvalue())
        checksum = root / (name + '.zip.CHECKSUM')
        checksum.write_text(sha256(archive) + '  ' + archive.name + '\n')
        return archive, checksum

    def test_header_and_headerless_complete_day(self):
        with tempfile.TemporaryDirectory() as d:
            for header in (False, True):
                a, c = self.archive(Path(d), header)
                self.assertEqual(len(validate_archive(a, c, 'ETHUSDT', self.day)), 1440)

    def test_bad_data_and_checksum_rejected(self):
        changes = [lambda r: r.pop(), lambda r: r[1].__setitem__(0, r[0][0]),
                   lambda r: r[0].__setitem__(0, r[0][0]*1000),
                   lambda r: r[0].__setitem__(2, 'NaN'),
                   lambda r: r[0].__setitem__(3, '4')]
        with tempfile.TemporaryDirectory() as d:
            for change in changes:
                a, c = self.archive(Path(d), change=change)
                with self.assertRaises(ValueError):
                    validate_archive(a, c, 'ETHUSDT', self.day)
            a, c = self.archive(Path(d))
            c.write_text('0'*64 + '  ' + a.name)
            with self.assertRaises(ValueError):
                validate_archive(a, c, 'ETHUSDT', self.day)

    def test_publish_separate_identity_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            a, c = self.archive(root)
            def fetch(url, path, limit):
                path.write_bytes((c if url.endswith('.CHECKSUM') else a).read_bytes())
            with patch('download_usdm_pilot.fetch_file', side_effect=fetch):
                m = download('ETHUSDT', self.day, date(2026, 9, 1), root/'out')
                self.assertEqual(m['venue'], 'binance_usdm')
                self.assertFalse(m['approved'])
                from research_cross_asset import verify
                with self.assertRaisesRegex(ValueError, 'Provenance mismatch'):
                    verify(list((root/'out').glob('*.csv')), 'ETHUSDT', 9999999999999)
                with self.assertRaises(ValueError):
                    download('ETHUSDT', self.day, date(2026, 9, 1), root/'out')
                with self.assertRaises(ValueError):
                    download('ETHUSDT', date(2026, 9, 1), date(2026, 9, 1), root/'reserved')
                self.assertFalse((root/'reserved').exists())

    def test_failed_download_does_not_publish(self):
        with tempfile.TemporaryDirectory() as d:
            with patch('download_usdm_pilot.fetch_file', side_effect=OSError('offline')):
                with self.assertRaises(OSError):
                    download('ETHUSDT', self.day, date(2026, 9, 1), Path(d)/'out')
            self.assertFalse((Path(d)/'out').exists())
