import tempfile
import unittest
from pathlib import Path
from engine_v1.core import Portfolio, Quote, dec
from engine_v1.operations import backup_database, process_lock
from restore_paper_ledger import restore

ACCOUNTS=[dict(id='one',symbol='BTCUSDT',capital='1000',notional='50')]


class LedgerRestoreTests(unittest.TestCase):
    def test_restored_backup_preserves_state_and_duplicate_protection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); original=root/'original.db'; backup=root/'backup.db'; dest=root/'restored.db'
            engine=Portfolio(original,ACCOUNTS)
            quote=Quote('BTCUSDT',dec('100'),dec('100'),dec('100'),dec('100'),1000,1)
            engine.process({'BTCUSDT':quote},{'one':{'enter':True}},1000,event_id='entry')
            # Back up while the source connection is open, including committed WAL.
            backup_database(original,backup)
            states=engine.states()
            risk=engine.db.execute('SELECT * FROM risk').fetchall()
            engine.close()
            before=backup.read_bytes()
            report=restore(backup,dest)
            self.assertEqual(report['events'],1)
            self.assertFalse(report['approved'])
            self.assertEqual(backup.read_bytes(),before)
            recovered=Portfolio(dest,ACCOUNTS)
            try:
                self.assertEqual(recovered.states(),states)
                self.assertEqual(recovered.db.execute('SELECT * FROM risk').fetchall(),risk)
                self.assertEqual(recovered.process({'BTCUSDT':quote},{'one':{'enter':True}},
                                                   1000,event_id='entry'),[])
                self.assertEqual(recovered.db.execute('SELECT count(*) FROM events').fetchone()[0],1)
            finally: recovered.close()

    def test_refuses_existing_destination_sidecars_and_active_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=root/'backup.db'; dest=root/'restored.db'
            Portfolio(source,ACCOUNTS).close()
            for suffix in ('','-wal','-shm','-journal'):
                artifact=Path(str(dest)+suffix); artifact.write_bytes(b'preserve')
                with self.assertRaises(ValueError): restore(source,dest)
                self.assertEqual(artifact.read_bytes(),b'preserve')
                artifact.unlink()
            with process_lock(str(dest)+'.lock'):
                with self.assertRaises(RuntimeError): restore(source,dest)
            self.assertFalse(dest.exists())

    def test_invalid_schema_does_not_publish(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=root/'wrong.db'; dest=root/'restored.db'
            db=sqlite3.connect(source); db.execute('CREATE TABLE other(x)'); db.close()
            with self.assertRaises(sqlite3.Error): restore(source,dest)
            self.assertFalse(dest.exists())

    def test_corrupt_or_missing_backup_does_not_publish(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=root/'bad.db'; dest=root/'restored.db'
            with self.assertRaises(ValueError): restore(source,dest)
            source.write_bytes(b'not a sqlite database')
            with self.assertRaises(sqlite3.Error): restore(source,dest)
            self.assertEqual(source.read_bytes(),b'not a sqlite database')
            self.assertFalse(dest.exists())
