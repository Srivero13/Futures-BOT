import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from audit_tradeflow import compare,run
from engine_v1.dataset import sha256
from train_v15 import timestamp


class FlowAlignmentTests(unittest.TestCase):
    def test_price_and_volume_comparison(self):
        flow=dict(taker_buy_qty='2',taker_sell_qty='1',first_price='100',last_price='101')
        candle=dict(open='100',close='101',high='101',low='99',volume='3')
        result=compare(flow,candle)
        self.assertTrue(result['volume_exact_match']);self.assertTrue(result['open_match'])
        candle['volume']='3.000000001'
        result=compare(flow,candle)
        self.assertFalse(result['volume_exact_match']);self.assertTrue(result['volume_within_tolerance'])
        candle.update(volume='4',close='102')
        result=compare(flow,candle)
        self.assertFalse(result['volume_within_tolerance']);self.assertFalse(result['close_match'])

    def test_complete_join_and_detect_corruption(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);start=timestamp('2026-08-01');flow=root/'ETHUSDT-aggTrades-2026-08-01-flow.csv'
            candle=root/'candles.csv';archive=root/'ETHUSDT-aggTrades-2026-08-01.zip';archive.write_bytes(b'fixture')
            fr=[];cr=[]
            for i in range(1440):
                ts=start//1000+i*60
                fr.append(dict(timestamp=ts,available_at_ms=(ts+60)*1000,agg_events=2,taker_buy_qty='2',taker_sell_qty='1',first_price='100',last_price='101'))
                cr.append(dict(timestamp=ts,open='100',close='101',high='101',low='100',volume='3'))
            def write(path,rows):
                with path.open('w') as f:
                    w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
            write(flow,fr);write(candle,cr)
            fm=root/'ETHUSDT-aggTrades-2026-08-01.json'
            meta=dict(venue='binance',market='spot',kind='aggTrades',symbol='ETHUSDT',date='2026-08-01',
                flow_sha256=sha256(flow),archive_sha256=sha256(archive),observed_minutes=1440,agg_events=2880,empty_minutes=0)
            fm.write_text(json.dumps(meta))
            candle.with_suffix('.json').write_text(json.dumps(dict(venue='binance',symbol='ETHUSDT',timeframe_ms=60000,
                last_open_ms=start+1439*60000,sha256=sha256(candle))))
            out=root/'out.json'
            with patch('sys.stdout'):
                report=run([flow],[candle],'ETHUSDT','2026-09-01',out)
                self.assertTrue(report['summary']['alignment_passed']);self.assertFalse(report['approved'])
                self.assertEqual(report['summary']['matched_minutes'],1440)
                with self.assertRaises(ValueError):run([flow],[candle],'ETHUSDT','2026-09-01',out)
                out.unlink();fr[0]['last_price']='102';write(flow,fr);meta['flow_sha256']=sha256(flow);fm.write_text(json.dumps(meta))
                report=run([flow],[candle],'ETHUSDT','2026-09-01',out)
                self.assertFalse(report['summary']['alignment_passed'])
                self.assertEqual(report['summary']['close_mismatches'],1)
                out.unlink();fr[0]['available_at_ms']=start;write(flow,fr);meta['flow_sha256']=sha256(flow);fm.write_text(json.dumps(meta))
                with self.assertRaisesRegex(ValueError,'premature'):run([flow],[candle],'ETHUSDT','2026-09-01',out)
                self.assertFalse(out.exists())
                with self.assertRaisesRegex(ValueError,'Reserved'):run([flow],[candle],'ETHUSDT','2026-08-01',out)


if __name__=='__main__':unittest.main()
