import sqlite3
import tempfile
import unittest
from pathlib import Path
from engine_v1.core import Portfolio, Quote, dec


ACCOUNTS=[dict(id=str(i),symbol='BTCUSDT',capital='1000',notional='50') for i in range(2)]
QUOTE=Quote('BTCUSDT',dec('100'),dec('100'),dec('100'),dec('100'),1000,1)
DECISIONS={str(i):{'enter':True} for i in range(2)}


class FaultConnection:
    def __init__(self, connection, error, at_commit=False, rollback_fails=False):
        self.connection=connection
        self.error=error
        self.at_commit=at_commit
        self.rollback_fails=rollback_fails
        self.injected=False
        self.closed=False
        self.account_updates=0

    def __getattr__(self,name):
        return getattr(self.connection,name)

    def execute(self,sql,*args):
        if sql.startswith('UPDATE accounts'):
            self.account_updates+=1
        if not self.injected and (
                (self.at_commit and sql=='COMMIT') or
                (not self.at_commit and sql.startswith('UPDATE accounts') and self.account_updates==2)):
            self.injected=True
            raise self.error
        if sql=='ROLLBACK' and self.rollback_fails:
            raise sqlite3.OperationalError('injected rollback failure')
        return self.connection.execute(sql,*args)

    def close(self):
        self.closed=True
        self.connection.close()


class LedgerRecoveryTests(unittest.TestCase):
    def recover(self,error,at_commit=False,rollback_fails=False):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'paper.db'
            engine=Portfolio(path,ACCOUNTS)
            before=engine.states()
            risk=engine.db.execute('SELECT state FROM risk').fetchone()
            faulty=FaultConnection(engine.db,error,at_commit,rollback_fails)
            engine.db=faulty
            with self.assertRaises(type(error)) as raised:
                engine.process({'BTCUSDT':QUOTE},DECISIONS,1000,event_id='retry')
            self.assertIs(raised.exception,error)
            self.assertEqual(faulty.account_updates,2)
            if rollback_fails:
                self.assertTrue(faulty.closed)
                self.assertTrue(error.__notes__)
            else:
                self.assertFalse(engine.db.in_transaction)
                self.assertEqual(engine.states(),before)
            engine.close()
            recovered=Portfolio(path,ACCOUNTS)
            try:
                self.assertEqual(recovered.states(),before)
                self.assertEqual(recovered.db.execute('SELECT state FROM risk').fetchone(),risk)
                for table in ('events','processed'):
                    self.assertEqual(recovered.db.execute(f'SELECT count(*) FROM {table}').fetchone()[0],0)
                results=recovered.process({'BTCUSDT':QUOTE},DECISIONS,1000,event_id='retry')
                self.assertEqual([r['action'] for r in results],['BUY','BUY'])
            finally: recovered.close()
            recovered=Portfolio(path,ACCOUNTS)
            try:
                saved=recovered.states()
                self.assertEqual(recovered.process({'BTCUSDT':QUOTE},DECISIONS,1000,event_id='retry'),[])
                self.assertEqual(recovered.states(),saved)
                self.assertEqual(recovered.db.execute('SELECT count(*) FROM events').fetchone()[0],2)
            finally: recovered.close()

    def test_interrupt_after_first_account_rolls_back(self):
        self.recover(KeyboardInterrupt())

    def test_database_failure_after_first_account_rolls_back(self):
        self.recover(sqlite3.OperationalError('injected write failure'))

    def test_failure_before_commit_rolls_back_all_accounts(self):
        self.recover(sqlite3.OperationalError('injected commit failure'),at_commit=True)

    def test_rollback_failure_closes_connection_preserves_original(self):
        self.recover(sqlite3.OperationalError('original'),rollback_fails=True)
