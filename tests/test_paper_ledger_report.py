import json
from pathlib import Path
import tempfile
import unittest
from engine_v1.core import Portfolio,Quote,dec
from report_paper_ledger import report


class PaperLedgerReportTests(unittest.TestCase):
    def setup_ledger(self,root):
        path=root/'paper.db'
        engine=Portfolio(path,[dict(id='a',symbol='BTCUSDT',capital='1000',notional='50'),
                               dict(id='b',symbol='ETHUSDT',capital='1000',notional='50')])
        return path,engine

    def quote(self,symbol,price,ts,seq):
        return Quote(symbol,dec(price),dec(price),dec('100'),dec('100'),ts,seq)

    def test_live_wal_roundtrip_and_open_position_reconcile_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path,p=self.setup_ledger(Path(tmp))
            try:
                p.process({s:self.quote(s,'100',1000,1) for s in ('BTCUSDT','ETHUSDT')},
                          {'a':{'enter':True},'b':{'enter':True}},1000,event_id='buy')
                p.process({'BTCUSDT':self.quote('BTCUSDT','101',2000,2)},
                          {'a':{'exit':True}},2000,event_id='sell')
                before=p.states()
                result=report(path)
                self.assertTrue(result['reconciled'])
                self.assertEqual(result['trade_events'],3)
                accounts={a['account']:a for a in result['accounts']}
                self.assertFalse(accounts['a']['open_position'])
                self.assertTrue(accounts['b']['open_position'])
                self.assertEqual(accounts['b']['last_recorded_mark_ms'],1000)
                self.assertEqual(accounts['a']['reconstructed']['sells'],1)
                self.assertEqual(accounts['a']['reconstructed']['realized'],before[0]['realized'])
                self.assertEqual(p.states(),before)
            finally:p.close()

    def test_modified_balance_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path,p=self.setup_ledger(Path(tmp))
            try:
                state=p.states()[0];state['cash']='999'
                p.db.execute('UPDATE accounts SET state=? WHERE id=?',(json.dumps(state),'a'))
                result=report(path)
                self.assertFalse(result['reconciled'])
                self.assertIn(dict(account='a',field='cash',scope='stored_account'),result['discrepancies'])
            finally:p.close()

    def test_empty_ledger_reconciles_and_missing_path_is_not_created(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path,p=self.setup_ledger(root);p.close()
            self.assertTrue(report(path)['reconciled'])
            self.assertEqual(report(path)['trade_events'],0)
            absent=root/'absent.db'
            with self.assertRaises(sqlite3.OperationalError):report(absent)
            self.assertFalse(absent.exists())

    def test_trade_payload_disagreement_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path,p=self.setup_ledger(Path(tmp))
            try:
                p.process({'BTCUSDT':self.quote('BTCUSDT','100',1000,1)},
                          {'a':{'enter':True}},1000,event_id='buy')
                event_id,raw=p.db.execute('SELECT id,payload FROM events').fetchone()
                trade=json.loads(raw);trade['cash']='0'
                p.db.execute('UPDATE events SET payload=? WHERE id=?',(json.dumps(trade),event_id))
                result=report(path)
                self.assertFalse(result['reconciled'])
                self.assertIn(dict(account='a',event_id=event_id,field='cash',scope='trade_payload'),
                              result['discrepancies'])
            finally:p.close()
