import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from record_basis_quotes import quote,pair,capture,feed
from queue import Queue
from threading import Event


def raw(**overrides):
    d=dict(s='ETHUSDT',u=1,b='100',a='101',B='2',A='3',e='bookTicker',E=100,T=99)
    d.update(overrides);return json.dumps(d)


class BasisQuoteTests(unittest.TestCase):
    def test_invalid_quotes(self):
        for update in (dict(s='BTCUSDT'),dict(b='NaN'),dict(B='0'),dict(b='102'),dict(u=True),dict(st=2)):
            with self.subTest(update=update),self.assertRaises(ValueError):
                quote(raw(**update),'usdm','ETHUSDT',1,2)

    def test_pair_requires_two_fresh_receipts(self):
        a=quote(raw(),'spot','ETHUSDT',1000000000,2)
        b=quote(raw(),'usdm','ETHUSDT',1100000000,3)
        self.assertIsNone(pair({'spot':a},1100000000))
        self.assertEqual(pair({'spot':a,'usdm':b},1200000000)['receipt_skew_ns'],100000000)
        self.assertIsNone(pair({'spot':a,'usdm':b},1300000000))
        self.assertIsNone(pair({'spot':a,'usdm':b},1050000000))

    def test_disconnect_sets_failure_and_closes(self):
        from unittest.mock import Mock
        ws=Mock();ws.recv.return_value=''
        stop=Event();errors=Queue()
        with patch('record_basis_quotes.websocket.create_connection',return_value=ws):
            feed('spot','url','ETHUSDT',Queue(),stop,errors)
        self.assertTrue(stop.is_set());self.assertEqual(errors.get()[1],'ConnectionError')
        ws.close.assert_called_once()

    def test_capture_saves_hashed_observation_and_refuses_existing_path(self):
        def fake(venue,url,symbol,queue,stop,errors):
            queue.put(quote(raw(),venue,symbol,time.monotonic_ns(),time.time_ns()))
        with tempfile.TemporaryDirectory() as tmp,patch('record_basis_quotes.feed',side_effect=fake):
            root=Path(tmp)/'capture'
            r=capture('ETHUSDT',1,root,1)
            self.assertTrue(r['capture_completed']);self.assertFalse(r['approved'])
            self.assertEqual(r['counts']['receipt_pairs'],1)
            import hashlib
            for part in r['parts']:
                data=(root/part['file']).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(),part['sha256'])
            with self.assertRaises(FileExistsError): capture('ETHUSDT',1,root,1)

    def test_feed_failure_never_reports_completed_capture(self):
        def fail(venue,url,symbol,queue,stop,errors):
            errors.put((venue,'ConnectionError'));stop.set()
        with tempfile.TemporaryDirectory() as tmp,patch('record_basis_quotes.feed',side_effect=fail):
            r=capture('ETHUSDT',1,Path(tmp)/'capture',1)
        self.assertFalse(r['capture_completed'])
        self.assertEqual(r['stop_reason'],'feed_failure')
        self.assertTrue(r['errors'])

    def test_queue_overflow_fails_instead_of_dropping_quotes(self):
        from unittest.mock import Mock
        ws=Mock();ws.recv.return_value=raw()
        q=Queue(maxsize=1);q.put('occupied');stop=Event();errors=Queue()
        with patch('record_basis_quotes.websocket.create_connection',return_value=ws):
            feed('spot','url','ETHUSDT',q,stop,errors)
        self.assertTrue(stop.is_set());self.assertEqual(errors.get()[1],'Full')
        ws.close.assert_called_once()
