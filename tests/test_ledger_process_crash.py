"""Abruptly terminate only a test-owned child using a temporary paper ledger."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from engine_v1.core import Portfolio, Quote, dec

ROOT=Path(__file__).resolve().parents[1]
ACCOUNTS=[dict(id=str(i),symbol='BTCUSDT',capital='1000',notional='50') for i in range(2)]
QUOTE=Quote('BTCUSDT',dec('100'),dec('100'),dec('100'),dec('100'),1000,1)
DECISIONS={str(i):{'enter':True} for i in range(2)}

WORKER=r"""
import json, sys, time
from pathlib import Path
from engine_v1.core import Portfolio, Quote, dec
path, marker, stage = sys.argv[1:]
accounts=[dict(id=str(i),symbol='BTCUSDT',capital='1000',notional='50') for i in range(2)]
engine=Portfolio(path,accounts)
quote=Quote('BTCUSDT',dec('100'),dec('100'),dec('100'),dec('100'),1000,1)
class PauseConnection:
    def __init__(self,db): self.db=db; self.updates=0
    def __getattr__(self,name): return getattr(self.db,name)
    def pause(self):
        marker_path=Path(marker)
        pending=marker_path.with_suffix('.pending')
        pending.write_text(json.dumps({'stage':stage,'transaction_open':self.db.in_transaction,
            'events':self.db.execute('SELECT count(*) FROM events').fetchone()[0],
            'processed':self.db.execute('SELECT count(*) FROM processed').fetchone()[0],
            'updates':self.updates}))
        pending.replace(marker_path)
        while True: time.sleep(1)
    def execute(self,sql,*args):
        if sql=='COMMIT' and stage=='before_commit': self.pause()
        result=self.db.execute(sql,*args)
        if sql.startswith('UPDATE accounts'):
            self.updates+=1
            if self.updates==1 and stage=='after_first_account': self.pause()
        if sql=='COMMIT' and stage=='after_commit': self.pause()
        return result
engine.db=PauseConnection(engine.db)
engine.process({'BTCUSDT':quote},{str(i):{'enter':True} for i in range(2)},1000,event_id='crash-event')
raise RuntimeError('Expected checkpoint was not reached')
"""


class ProcessCrashTests(unittest.TestCase):
    def exercise(self,stage):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); path=root/'paper.db'; marker=root/'ready.json'
            initial=Portfolio(path,ACCOUNTS)
            clean_states=initial.states()
            clean_risk=initial.db.execute('SELECT state FROM risk').fetchone()
            initial.close()
            # Compute the expected committed state using the real ledger engine.
            reference=Portfolio(':memory:',ACCOUNTS)
            reference.process({'BTCUSDT':QUOTE},DECISIONS,1000,event_id='crash-event')
            committed_states=reference.states()
            committed_risk=reference.db.execute('SELECT state FROM risk').fetchone()
            reference.close()
            with (root/'worker.log').open('w+') as log:
                child=subprocess.Popen([sys.executable,'-u','-c',WORKER,str(path),str(marker),stage],
                                       cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
                try:
                    deadline=time.monotonic()+10
                    while not marker.exists() and child.poll() is None and time.monotonic()<deadline:
                        time.sleep(.01)
                    if not marker.exists():
                        log.seek(0)
                        self.fail('Worker did not reach checkpoint: '+log.read())
                    checkpoint=json.loads(marker.read_text())
                    self.assertEqual(checkpoint['stage'],stage)
                    self.assertEqual(checkpoint['transaction_open'],stage!='after_commit')
                    self.assertEqual(checkpoint['updates'],1 if stage=='after_first_account' else 2)
                    self.assertEqual(checkpoint['events'],0 if stage=='after_first_account' else 2)
                    self.assertEqual(checkpoint['processed'],0 if stage=='after_first_account' else 2)
                    child.kill()  # SIGKILL on POSIX; no Python rollback/finally runs.
                    child.wait(timeout=5)
                    self.assertNotEqual(child.returncode,0)
                finally:
                    if child.poll() is None:
                        child.kill()
                        child.wait(timeout=5)
            recovered=Portfolio(path,ACCOUNTS)
            try:
                self.assertEqual(recovered.db.execute('PRAGMA integrity_check').fetchone(),('ok',))
                committed=stage=='after_commit'
                self.assertEqual(recovered.states(),committed_states if committed else clean_states)
                self.assertEqual(recovered.db.execute('SELECT state FROM risk').fetchone(),
                                 committed_risk if committed else clean_risk)
                for table in ('events','processed'):
                    self.assertEqual(recovered.db.execute(f'SELECT count(*) FROM {table}').fetchone()[0],
                                     2 if committed else 0)
                results=recovered.process({'BTCUSDT':QUOTE},DECISIONS,1000,event_id='crash-event')
                self.assertEqual([r['action'] for r in results],[] if committed else ['BUY','BUY'])
                self.assertEqual(recovered.states(),committed_states)
                self.assertEqual(recovered.db.execute('SELECT count(*) FROM events').fetchone()[0],2)
            finally: recovered.close()

    def test_kill_after_first_account_discards_partial_transaction(self):
        self.exercise('after_first_account')

    def test_kill_before_commit_discards_all_pending_writes(self):
        self.exercise('before_commit')

    def test_kill_after_commit_preserves_trades_and_deduplication(self):
        self.exercise('after_commit')
