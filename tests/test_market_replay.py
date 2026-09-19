import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from record_market import Writer
from replay_market import Book,replay


class ReplayTests(unittest.TestCase):
    def snapshot(self):
        return {'lastUpdateId':100,'bids':[['99','2'],['98','3']],'asks':[['101','4'],['102','5']]}

    def test_absolute_quantity_deletion_and_coverage(self):
        book=Book(self.snapshot())
        status,q=book.update({'U':101,'u':101,'b':[['99','7']],'a':[]})
        self.assertEqual(str(q[2]),'7')
        book.update({'U':102,'u':102,'b':[['99','0'],['98','0'],['97','10']],'a':[]})
        self.assertIsNone(book.quote())
        self.assertNotIn(97,book.bids)
        with self.assertRaisesRegex(ValueError,'gap'):book.update({'U':104,'u':104,'b':[],'a':[]})
        book=Book(self.snapshot())
        with self.assertRaisesRegex(ValueError,'Crossed'):book.update({'U':101,'u':101,'b':[['102','1']],'a':[]})

    def test_manifest_replay_corruption_and_counts(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);writer=Writer(root,limit=100000,reserve=0)
            records=[{'kind':'session_start'}, {'kind':'snapshot','data':self.snapshot()},
                {'kind':'depthUpdate','sequence_status':'stale','data':{'e':'depthUpdate','s':'ETHUSDT','U':99,'u':100,'b':[],'a':[]}},
                {'kind':'depthUpdate','sequence_status':'linked','data':{'e':'depthUpdate','s':'ETHUSDT','U':101,'u':102,'b':[['99','5']],'a':[]}},
                {'kind':'aggTrade','data':{'e':'aggTrade','s':'ETHUSDT','a':42,'p':'100','q':'1'}}]
            for i,r in enumerate(records):writer.write(dict(r,session=1,receipt_monotonic_ns=i+1,receipt_wall_ns=i+1))
            writer.close_part()
            summary={'parts':writer.parts,'event_bytes':writer.total,'counts':{'snapshots':1,'depth_stale':1,'depth_linked':1,'agg_trades':1}}
            (root/'summary.json').write_text(json.dumps(summary));(root/'protocol.json').write_text(json.dumps({'symbol':'ETHUSDT'}))
            with patch('builtins.print'):report=replay(root,root/'result.json')
            self.assertTrue(report['integrity_passed']);self.assertEqual(report['counts']['covered_quotes'],1)
            self.assertEqual(report['covered_quote_spread_bps']['mean'],200)
            with self.assertRaises(ValueError):replay(root,root/'result.json')
            summary['counts']['agg_trades']=2;(root/'summary.json').write_text(json.dumps(summary))
            with patch('builtins.print'),self.assertRaisesRegex(ValueError,'count mismatch'):replay(root,root/'bad-count.json')
            part=root/writer.parts[0]['file'];part.write_bytes(part.read_bytes()+b'x')
            with patch('builtins.print'),self.assertRaisesRegex(ValueError,'Corrupt'):replay(root,root/'bad-hash.json')
