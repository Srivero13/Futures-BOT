import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from record_market import DepthSequence,Writer,StorageLimit


class RecorderTests(unittest.TestCase):
    def test_snapshot_bridge_overlap_stale_gap_and_reset(self):
        seq=DepthSequence(100)
        self.assertEqual(seq.accept(98,100),'stale');self.assertFalse(seq.bridged)
        self.assertEqual(seq.accept(99,102),'linked');self.assertTrue(seq.bridged)
        self.assertEqual(seq.accept(102,104),'linked')
        with self.assertRaises(ValueError):seq.accept(106,107)
        self.assertEqual(seq.last,104)
        reset=DepthSequence(200)
        self.assertEqual(reset.accept(199,201),'linked')
        with self.assertRaises(ValueError):reset.accept(205,202)

    def test_storage_rotation_hash_and_budget(self):
        with tempfile.TemporaryDirectory() as d:
            w=Writer(d,limit=50,chunk=20,reserve=0)
            w.write({'a':1});w.write({'a':2});w.write({'a':3})
            with self.assertRaises(StorageLimit):w.write({'large':'x'*100})
            w.close_part()
            self.assertEqual(len(w.parts),2)
            self.assertEqual(sum(p['bytes'] for p in w.parts),w.total)
            for part in w.parts:
                data=(Path(d)/part['file']).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(),part['sha256'])
                for line in data.splitlines():json.loads(line)

    def test_capture_reconnects_with_new_snapshot_and_retains_gap(self):
        from unittest.mock import patch,MagicMock
        from record_market import capture
        def event(first,last):
            return json.dumps({'data':{'e':'depthUpdate','s':'ETHUSDT','U':first,'u':last,'b':[],'a':[]}})
        first=MagicMock();first.recv.side_effect=[event(100,102),event(105,106)]
        second=MagicMock();second.recv.side_effect=[event(199,201),KeyboardInterrupt()]
        response1=MagicMock();response1.__enter__.return_value.read.return_value=json.dumps({'lastUpdateId':100,'bids':[],'asks':[]}).encode()
        response2=MagicMock();response2.__enter__.return_value.read.return_value=json.dumps({'lastUpdateId':200,'bids':[],'asks':[]}).encode()
        with tempfile.TemporaryDirectory() as d,patch('record_market.websocket.create_connection',side_effect=[first,second]),patch('record_market.urlopen',side_effect=[response1,response2]),patch('record_market.time.sleep'),patch('builtins.print'):
            root=Path(d)/'capture'
            report=capture('ETHUSDT',60,root,1024**2)
            self.assertEqual(report['stop_reason'],'interrupted')
            self.assertEqual(report['counts']['snapshots'],2)
            self.assertEqual(report['counts']['depth_linked'],2)
            self.assertEqual(report['counts']['depth_gap_or_invalid'],1)
            self.assertEqual(report['errors']['depth_sequence_gap'],1)
            rows=[json.loads(line) for line in (root/'events-00000.jsonl').read_text().splitlines()]
            self.assertEqual(sum(r['kind']=='snapshot' for r in rows),2)
            self.assertTrue(any(r.get('sequence_status')=='gap_or_invalid' for r in rows))
            first.close.assert_called_once();second.close.assert_called_once()
