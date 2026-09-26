import json
import os
import signal
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from engine_v1.processes import run_workers, WorkerFailure
from engine_v1.operations import atomic_json


def job(root, name, code):
    return {'name': name, 'argv': [sys.executable, '-u', '-c', code], 'log': root/f'{name}.log'}


class ProcessSupervisionTests(unittest.TestCase):
    def options(self):
        return dict(poll_seconds=.02, heartbeat_seconds=10, grace_seconds=.1)

    def assert_reaped(self, status):
        for worker in status['workers']:
            if worker['pid'] is not None:
                self.assertIsNotNone(worker['returncode'])
                if os.name == 'posix':
                    with self.assertRaises(ProcessLookupError):
                        os.kill(worker['pid'], 0)

    def test_success_logs_and_status_without_argv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            codes = run_workers([job(root, 'one', 'print("done")'),
                                 job(root, 'two', 'print("also done")')], root/'status.json', 5, **self.options())
            self.assertEqual(codes, [0, 0])
            self.assertIn('done', (root/'one.log').read_text())
            status = json.loads((root/'status.json').read_text())
            self.assertEqual(status['state'], 'succeeded')
            self.assertFalse(status['approved'])
            self.assertNotIn('argv', status['workers'][0])
            self.assert_reaped(status)

    def test_second_worker_failure_stops_first_instead_of_waiting_for_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            began = time.monotonic()
            with self.assertRaises(WorkerFailure):
                run_workers([job(root, 'blocked', 'import time; time.sleep(60)'),
                             job(root, 'failed', 'raise SystemExit(3)')], root/'status.json', 10, **self.options())
            self.assertLess(time.monotonic()-began, 5)
            status = json.loads((root/'status.json').read_text())
            self.assertEqual(status['state'], 'failed')
            self.assertEqual(status['workers'][1]['returncode'], 3)
            self.assert_reaped(status)

    @unittest.skipUnless(os.name == 'posix', 'POSIX termination escalation')
    def test_deadline_kills_worker_ignoring_termination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code = 'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print("ready"); time.sleep(60)'
            with self.assertRaises(WorkerFailure):
                run_workers([job(root, 'stuck', code)], root/'status.json', .7, **self.options())
            status = json.loads((root/'status.json').read_text())
            self.assertEqual(status['state'], 'timed_out')
            self.assertIn('ready', (root/'stuck.log').read_text())
            self.assertEqual(status['workers'][0]['returncode'], -9)
            self.assert_reaped(status)

    def test_partial_launch_failure_cleans_up_started_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bad = {'name': 'bad', 'argv': [str(root/'missing-executable')], 'log': root/'bad.log'}
            with self.assertRaises(OSError):
                run_workers([job(root, 'started', 'import time; time.sleep(60)'), bad],
                            root/'status.json', 5, **self.options())
            status = json.loads((root/'status.json').read_text())
            self.assertEqual(status['reason'], 'supervisor_or_launch_error')
            self.assert_reaped(status)

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux process-group cleanup check')
    def test_timeout_also_stops_worker_descendant(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            descendant = 'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)'
            code = ('import subprocess,sys,time; '
                    f'p=subprocess.Popen([sys.executable,"-c",{descendant!r}]); '
                    'print("DESCENDANT="+str(p.pid),flush=True); time.sleep(60)')
            with self.assertRaises(WorkerFailure):
                run_workers([job(root, 'parent', code)], root/'status.json', .7, **self.options())
            lines = (root/'parent.log').read_text().splitlines()
            pid = int(next(line.split('=', 1)[1] for line in lines if line.startswith('DESCENDANT=')))
            proc = Path(f'/proc/{pid}/stat')
            # An orphan may await PID 1 reaping; it must no longer be executing.
            deadline = time.monotonic()+2
            while proc.exists() and proc.read_text().split(') ', 1)[1][0] != 'Z' and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(not proc.exists() or proc.read_text().split(') ', 1)[1][0] == 'Z')

    @unittest.skipUnless(os.name == 'posix', 'POSIX SIGTERM handling')
    def test_sigterm_interrupts_and_restores_handler(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = signal.getsignal(signal.SIGTERM)
            original_sleep = time.sleep
            sent = False
            def send_once(seconds):
                nonlocal sent
                if not sent:
                    sent = True
                    os.kill(os.getpid(), signal.SIGTERM)
                original_sleep(seconds)
            with patch('engine_v1.processes.time.sleep', side_effect=send_once):
                with self.assertRaises(KeyboardInterrupt):
                    run_workers([job(root, 'started', 'import time; time.sleep(60)')],
                                root/'status.json', 5, **self.options())
            status = json.loads((root/'status.json').read_text())
            self.assertEqual(status['state'], 'interrupted')
            self.assertEqual(signal.getsignal(signal.SIGTERM), previous)
            self.assert_reaped(status)

    def test_status_write_failure_stops_workers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = 0
            def publish(path, value):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError('simulated disk failure')
                atomic_json(path, value)
            with patch('engine_v1.processes.atomic_json', side_effect=publish):
                with self.assertRaises(OSError):
                    run_workers([job(root, 'started', 'import time; time.sleep(60)')],
                                root/'status.json', 5, **self.options())
            self.assert_reaped(json.loads((root/'status.json').read_text()))

    def test_interrupt_cleans_up_and_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sleep = time.sleep
            interrupted = False
            def interrupt_once(seconds):
                nonlocal interrupted
                if not interrupted:
                    interrupted = True
                    raise KeyboardInterrupt
                sleep(seconds)
            with patch('engine_v1.processes.time.sleep', side_effect=interrupt_once):
                with self.assertRaises(KeyboardInterrupt):
                    run_workers([job(root, 'started', 'import time; time.sleep(60)')],
                                root/'status.json', 5, **self.options())
            status = json.loads((root/'status.json').read_text())
            self.assertEqual(status['state'], 'interrupted')
            self.assert_reaped(status)
            before = (root/'status.json').read_bytes()
            with self.assertRaises(ValueError):
                run_workers([job(root, 'new', 'pass')], root/'status.json', 5)
            self.assertEqual(before, (root/'status.json').read_bytes())

    def test_invalid_deadlines_rejected_before_launch(self):
        for timeout in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                run_workers([], Path('unused.json'), timeout)
