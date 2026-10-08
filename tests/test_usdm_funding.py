from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlparse, parse_qs

from download_usdm_funding import download, timestamp, validate_page


class FundingTests(unittest.TestCase):
    start, end = date(2026, 8, 1), date(2026, 8, 8)

    def row(self, t, **changes):
        return dict(symbol='ETHUSDT', fundingTime=t, fundingRate='-0.0001', markPrice='2500', **changes)

    def test_invalid_pages_rejected(self):
        t = timestamp(self.start)
        good = self.row(t)
        for payload in ({'code': -1}, [good, good], [dict(good, symbol='BTCUSDT')],
                        [dict(good, fundingTime=t*1000)], [dict(good, fundingRate='NaN')],
                        [dict(good, markPrice='0')], [dict(good, fundingTime=True)]):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                validate_page(payload, 'ETHUSDT', t, timestamp(self.end))

    def test_negative_rate_and_missing_mark_preserved(self):
        t = timestamp(self.start)
        row = self.row(t)
        row.pop('markPrice')
        r = validate_page([row], 'ETHUSDT', t, timestamp(self.end))[0]
        self.assertEqual(r['funding_rate'], '-0.0001')
        self.assertIsNone(r['mark_price'])

    def test_pagination_inclusive_bounds_and_publication(self):
        t = timestamp(self.start)
        urls = []
        def fetch(url, path, limit):
            urls.append(parse_qs(urlparse(url).query))
            rows = [self.row(t+i*1000) for i in range(1000)] if len(urls)==1 else [self.row(t+1000000)]
            path.write_text(json.dumps(rows))
        with tempfile.TemporaryDirectory() as d, patch('download_usdm_funding.fetch_file', side_effect=fetch):
            out = Path(d)/'out'
            report = download('ETHUSDT', self.start, self.end, date(2026,9,1), out)
            self.assertEqual(report['records'], 1001)
            self.assertEqual(int(urls[1]['startTime'][0]), t+999000+1)
            self.assertEqual(int(urls[0]['endTime'][0]), timestamp(self.end)-1)
            self.assertFalse(report['schedule_coverage_verified'])
            self.assertEqual(len(list(out.glob('page-*.json'))), 2)
            with self.assertRaises(ValueError):
                download('ETHUSDT', self.start, self.end, date(2026,9,1), out)

    def test_empty_and_network_failure_do_not_publish(self):
        for error in (False, True):
            def fetch(url, path, limit):
                if error:
                    raise OSError('offline')
                path.write_text('[]')
            with tempfile.TemporaryDirectory() as d, patch('download_usdm_funding.fetch_file', side_effect=fetch):
                out=Path(d)/'out'
                with self.assertRaises((ValueError, OSError)):
                    download('ETHUSDT', self.start, self.end, date(2026,9,1), out)
                self.assertFalse(out.exists())

    def test_reserve_and_budget_rejected_before_network(self):
        with tempfile.TemporaryDirectory() as d, patch('download_usdm_funding.fetch_file') as fetch:
            for end, reserve in ((date(2026,8,9), date(2026,9,1)), (self.end, date(2026,8,5))):
                with self.assertRaises(ValueError):
                    download('ETHUSDT', self.start, end, reserve, Path(d)/'out')
            fetch.assert_not_called()
