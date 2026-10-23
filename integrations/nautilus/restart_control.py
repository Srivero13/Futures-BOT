"""Crash/reopen a paper admission journal and reconcile a separate durable replay."""
import argparse
import json
import os
import subprocess
import sys
from decimal import Decimal as D
from pathlib import Path

from .durable import DurableAdmission
from .paper_control import run as paper_run


def crash_worker(path):
    gate = DurableAdmission(path)
    gate.last.update(A=10**9, B=10**9)
    if not gate.request('A', 'entry-a', 10**9, D('100')) or not gate.request('B', 'entry-b', 10**9, D('40')):
        raise ValueError('Unable to prepare pending entries')
    gate.paused = True
    if not gate.request('A', 'exit-a', 10**9, D('100'), exit=True):
        raise ValueError('Unable to prepare pending exit')
    os._exit(23)  # Deliberately bypass finally/SQLite close; no exchange process exists.


def run(root):
    root.mkdir(parents=True, exist_ok=False)
    child = subprocess.run([sys.executable, '-m', 'integrations.nautilus.restart_control',
                            '--crash-worker', str(root/'pending.sqlite3')],
                           capture_output=True, text=True, timeout=30)
    (root/'worker.log').write_text(child.stdout+child.stderr)
    if child.returncode != 23:
        raise ValueError('Crash fixture failed; inspect worker.log')
    gate = DurableAdmission(root/'pending.sqlite3')
    try:
        checks = dict(pause_restored=gate.paused,
                      reservations_restored=gate.reserved == {'A': D('100'), 'B': D('40')},
                      duplicate_ids_restored=gate.seen == {('A','entry-a'),('B','entry-b'),('A','exit-a')},
                      exit_pending_restored=gate.exits_pending == {'A'},
                      old_quotes_discarded=gate.last == {},
                      reconciliation_required=gate.reconciliation_required,
                      sqlite_integrity=gate.db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok')
        gate.last.update(A=2*10**9, B=2*10**9)
        gate.paused = False
        checks['fresh_quotes_and_unpause_do_not_bypass_restart_guard'] = not gate.request(
            'B', 'new-entry', 2*10**9, D('1'))
        checks['reservations_not_forgotten'] = gate.reserved == {'A': D('100'), 'B': D('40')}
    finally:
        gate.close()
    durable = DurableAdmission(root/'replay.sqlite3')
    try:
        replay = paper_run(durable)
    finally:
        durable.close()
    restored = DurableAdmission(root/'replay.sqlite3')
    try:
        checks['completed_replay_reopens_flat'] = not restored.reserved and not restored.exits_pending
        checks['completed_replay_duplicate_retained'] = ('A', 'enter-a') in restored.seen
        checks['flat_restart_requires_new_quotes'] = restored.last == {}
    finally:
        restored.close()
    if not all(checks.values()):
        raise ValueError(f'Restart control failed: {checks}')
    report = dict(approved=False, real_orders=False, synthetic=True,
                  status='durable_paper_control_passed', checks=checks,
                  paper_replay_checks=replay['checks'], paper_balances=replay['balances'],
                  limitations=['Restores admission state only, not Nautilus orders, positions or cash.',
                               'Pending state after restart blocks all requests until explicit future reconciliation support.',
                               'Process-exit/WAL control; not an OS crash, power-loss or live-exchange test.'])
    (root/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--crash-worker', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.crash_worker:
        crash_worker(args.crash_worker)
    if args.output_dir is None:
        parser.error('--output-dir is required')
    print(json.dumps(run(args.output_dir.resolve()), indent=2))


if __name__ == '__main__':
    main()
