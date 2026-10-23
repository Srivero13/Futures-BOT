import sqlite3
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path

from integrations.nautilus.durable import DurableAdmission
from integrations.nautilus.restart_control import run


class DurableTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'admission.sqlite3'

    def test_process_exit_and_real_nautilus_durable_replay(self):
        result = run(Path(self.temp.name)/'control')
        self.assertTrue(all(result['checks'].values()))
        self.assertTrue(all(result['paper_replay_checks'].values()))
        self.assertFalse(result['approved'])

    def test_second_writer_refused(self):
        first = DurableAdmission(self.path)
        try:
            with self.assertRaises(BlockingIOError):
                DurableAdmission(self.path)
        finally:
            first.close()

    def test_audit_write_failure_rolls_back_state_and_memory(self):
        gate = DurableAdmission(self.path)
        try:
            gate.last.update(A=10**9, B=10**9)
            gate.db.execute("CREATE TRIGGER fail_audit BEFORE INSERT ON admission_audit BEGIN SELECT RAISE(ABORT, 'injected'); END")
            with self.assertRaises(sqlite3.IntegrityError):
                gate.request('A', 'entry', 10**9, D('100'))
            self.assertEqual(gate.reserved, {})
            self.assertEqual(gate.seen, frozenset())
        finally:
            gate.close()
        restored = DurableAdmission(self.path)
        try:
            self.assertEqual(restored.reserved, {})
            self.assertFalse(restored.reconciliation_required)
        finally:
            restored.close()

    def test_reopened_pending_position_cannot_release_without_reconciliation(self):
        gate = DurableAdmission(self.path)
        gate.last.update(A=10**9, B=10**9)
        gate.request('A', 'entry', 10**9, D('100'))
        gate.close()
        restored = DurableAdmission(self.path)
        try:
            with self.assertRaisesRegex(ValueError, 'reconciliation'):
                restored.confirm_flat('A')
            self.assertEqual(restored.reserved, {'A': D('100')})
        finally:
            restored.close()

    def test_corrupt_state_is_not_reset(self):
        gate = DurableAdmission(self.path)
        gate.db.execute("UPDATE admission SET state='{}'")
        gate.close()
        with self.assertRaises(ValueError):
            DurableAdmission(self.path)
        connection = sqlite3.connect(self.path)
        try:
            self.assertEqual(connection.execute('SELECT state FROM admission').fetchone()[0], '{}')
        finally:
            connection.close()


if __name__ == '__main__':
    unittest.main()
