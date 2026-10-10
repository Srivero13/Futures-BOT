from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlparse,parse_qs
from download_usdm_marks import parse_page,download
from download_usdm_funding import timestamp


class MarkTests(unittest.TestCase):
    def row(self,t):
        return [t,'100','102','99','101','0',t+59999,'0',0,'0','0','0']

    def test_parser_rejects_gaps_nonfinite_and_bad_bounds(self):
        for index,value in [(0,60000),(2,'NaN'),(3,'103'),(6,0)]:
            row=self.row(0);row[index]=value
            with self.assertRaises(ValueError):
                parse_page([row],0,86400000)
        self.assertEqual(parse_page([self.row(0)],0,86400000)[0]['close'],'101')

    def test_paginated_full_day_and_no_overwrite(self):
        day=date(2026,8,1);start=timestamp(day);urls=[]
        def fetch(url,path,limit):
            params=parse_qs(urlparse(url).query);cursor=int(params['startTime'][0]);urls.append(url)
            path.write_text(json.dumps([self.row(t) for t in range(cursor,min(cursor+60000000,start+86400000),60000)]))
        with tempfile.TemporaryDirectory() as d,patch('download_usdm_marks.fetch_file',side_effect=fetch):
            out=Path(d)/'marks';r=download('ETHUSDT',day,date(2026,9,1),out)
            self.assertEqual(r['rows'],1440);self.assertEqual(len(urls),2)
            self.assertEqual(r['kind'],'mark_price_1m');self.assertFalse(r['approved'])
            with self.assertRaises(ValueError):
                download('ETHUSDT',day,date(2026,9,1),out)

    def test_incomplete_day_and_reserve_do_not_publish(self):
        with tempfile.TemporaryDirectory() as d,patch('download_usdm_marks.fetch_file',side_effect=lambda u,p,limit:p.write_text('[]')):
            out=Path(d)/'marks'
            with self.assertRaises(ValueError):
                download('ETHUSDT',date(2026,8,1),date(2026,9,1),out)
            self.assertFalse(out.exists())
            with self.assertRaises(ValueError):
                download('ETHUSDT',date(2026,9,1),date(2026,9,1),out)
