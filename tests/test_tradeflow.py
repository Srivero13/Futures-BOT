import csv
import io
from datetime import datetime,timezone
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from download_tradeflow import convert,download_day,run,fetch,GIB


def make_zip(path,rows):
    with zipfile.ZipFile(path,'w') as z:z.writestr('source.csv','\n'.join(','.join(map(str,r)) for r in rows)+'\n')


class TradeflowTests(unittest.TestCase):
    def test_units_direction_and_close_availability(self):
        for year in (2024,2026):
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);day=datetime(year,8,1,tzinfo=timezone.utc)
                factor=1000 if year==2024 else 1000000
                ts=int(day.timestamp())*factor
                archive=root/'a.zip';output=root/'flow.csv'
                make_zip(archive,[[1,100,2,10,11,ts,'false','true'],[2,110,1,12,12,ts+factor,'true','true'],
                                  [4,105,3,13,15,ts+60*factor,'false','true']])
                r=convert(archive,output,day,root,GIB)
                with output.open() as f:rows=list(csv.DictReader(f))
                self.assertEqual(rows[0]['taker_buy_qty'],'2');self.assertEqual(rows[0]['taker_sell_qty'],'1')
                self.assertEqual(rows[0]['taker_buy_quote'],'200');self.assertEqual(rows[0]['taker_sell_quote'],'110')
                self.assertAlmostEqual(float(rows[0]['volume_imbalance']),1/3)
                self.assertEqual(int(rows[0]['available_at_ms']),(int(day.timestamp())+60)*1000)
                self.assertEqual(r['observed_minutes'],2);self.assertEqual(r['aggregate_id_gaps'],1)
                self.assertEqual(rows[0]['trade_id_span_count'],'3')

    def test_bad_records_and_zip_limit(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);day=datetime(2026,8,1,tzinfo=timezone.utc);ts=int(day.timestamp())*1000000
            base=[1,100,1,1,1,ts,'false','true']
            for index,value in [(1,'NaN'),(2,-1),(5,ts//1000),(6,'maybe')]:
                row=list(base);row[index]=value;make_zip(root/'a.zip',[row])
                with self.assertRaises(ValueError):convert(root/'a.zip',root/'out.csv',day,root,GIB)
            make_zip(root/'a.zip',[base,base])
            with self.assertRaises(ValueError):convert(root/'a.zip',root/'out.csv',day,root,GIB)
            with self.assertRaises(ValueError):convert(root/'a.zip',root/'out.csv',day,root,GIB,max_uncompressed=1)

    def test_checksum_publication_resume_and_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);day=datetime(2026,8,1,tzinfo=timezone.utc);ts=int(day.timestamp())*1000000
            fixture=root/'fixture.zip';make_zip(fixture,[[1,100,1,1,1,ts,'false','true']])
            payload=fixture.read_bytes();fixture.unlink();digest=hashlib.sha256(payload).hexdigest()
            def fetch(url,path,*args):
                path.write_bytes((digest+'  ETHUSDT-aggTrades-2026-08-01.zip\n').encode() if url.endswith('CHECKSUM') else payload)
            with patch('download_tradeflow.fetch',side_effect=fetch),patch('sys.stdout'):
                first=download_day(root,'ETHUSDT',day,GIB,1024**2)
            with patch('download_tradeflow.fetch') as net,patch('sys.stdout'):
                self.assertEqual(first,download_day(root,'ETHUSDT',day,GIB,1024**2));net.assert_not_called()
                (root/'ETHUSDT-aggTrades-2026-08-01-flow.csv').write_text('corrupt')
                with self.assertRaises(ValueError):download_day(root,'ETHUSDT',day,GIB,1024**2)

    def test_bad_checksum_no_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);day=datetime(2026,8,1,tzinfo=timezone.utc)
            def fetch(url,path,*args):
                path.write_bytes(('0'*64+'  ETHUSDT-aggTrades-2026-08-01.zip').encode() if url.endswith('CHECKSUM') else b'bad')
            with patch('download_tradeflow.fetch',side_effect=fetch),patch('sys.stdout'):
                with self.assertRaises(ValueError):download_day(root,'ETHUSDT',day,GIB,1024**2)
            self.assertFalse(list(root.glob('*.json')));self.assertFalse(list(root.glob('*.partial')))

    def test_network_size_limit_cleans_partial(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);part=root/'download.partial'
            with patch('download_tradeflow.urlopen',return_value=io.BytesIO(b'1234')):
                with self.assertRaisesRegex(ValueError,'size limit'):
                    fetch('https://example.com/data',part,root,GIB,3)
            self.assertFalse(part.exists())

    def test_reserved_boundary_before_network(self):
        with patch('download_tradeflow.fetch') as fetch:
            with self.assertRaises(ValueError):run('unused','ETHUSDT','2026-08-31','2026-09-02','2026-09-01')
            fetch.assert_not_called()


if __name__=='__main__':unittest.main()
