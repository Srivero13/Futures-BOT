"""Durable paper admission journal. This does not restore Nautilus positions."""
import fcntl
import json
import sqlite3
from decimal import Decimal as D
from pathlib import Path

from .paper_control import Admission

POLICY = 'nautilus-paper-admission-v1-account120-global150'


def encode(gate):
    return dict(paused=gate.paused, reserved={k: str(v) for k, v in gate.reserved.items()},
                seen=sorted([list(k) for k in gate.seen]),
                exits_pending=sorted(gate.exits_pending), peak_reserved=str(gate.peak_reserved))


def decode(state):
    gate = Admission()
    if set(state) != {'paused', 'reserved', 'seen', 'exits_pending', 'peak_reserved'} or type(state['paused']) is not bool:
        raise ValueError('Invalid journal state')
    gate.paused = state['paused']
    for account, amount in state['reserved'].items():
        if account not in ('A', 'B') or not isinstance(amount, str):
            raise ValueError('Invalid reservation')
        amount = D(amount)
        if not amount.is_finite() or not 0 < amount <= 120:
            raise ValueError('Invalid reservation amount')
        gate.reserved[account] = amount
    if sum(gate.reserved.values(), D(0)) > 150:
        raise ValueError('Journal exceeds global cap')
    for key in state['seen']:
        if not isinstance(key, list) or len(key) != 2 or key[0] not in ('A', 'B') or not isinstance(key[1], str) or not key[1]:
            raise ValueError('Invalid duplicate state')
        gate.seen.add(tuple(key))
    gate.exits_pending = set(state['exits_pending'])
    if not gate.exits_pending <= set(gate.reserved):
        raise ValueError('Exit without reservation')
    gate.peak_reserved = D(state['peak_reserved'])
    if not gate.peak_reserved.is_finite() or not sum(gate.reserved.values(), D(0)) <= gate.peak_reserved <= 150:
        raise ValueError('Invalid peak reservation')
    return gate


class DurableAdmission:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = self.path.with_suffix(self.path.suffix+'.lock').open('a')
        self.db = None
        try:
            fcntl.flock(self._lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.db = sqlite3.connect(self.path, isolation_level=None)
            self.db.execute('PRAGMA journal_mode=WAL')
            self.db.execute('PRAGMA synchronous=FULL')
            self.db.execute('CREATE TABLE IF NOT EXISTS admission (id INTEGER PRIMARY KEY CHECK(id=1), policy TEXT NOT NULL, state TEXT NOT NULL)')
            self.db.execute('CREATE TABLE IF NOT EXISTS admission_audit (id INTEGER PRIMARY KEY, action TEXT NOT NULL, payload TEXT NOT NULL)')
            row = self.db.execute('SELECT policy,state FROM admission WHERE id=1').fetchone()
            if row is None:
                gate = Admission()
                self.db.execute('INSERT INTO admission VALUES(1,?,?)', (POLICY, json.dumps(encode(gate))))
            else:
                if row[0] != POLICY:
                    raise ValueError('Journal policy mismatch')
                gate = decode(json.loads(row[1]))
            self._gate = gate
            # Receipt timestamps never survive a process restart.
            self.last = {}
            self.reconciliation_required = bool(gate.reserved)
        except BaseException:
            self.close()
            raise

    @property
    def paused(self):
        return self._gate.paused

    @paused.setter
    def paused(self, value):
        if type(value) is not bool:
            raise ValueError('Pause must be boolean')
        self._change('pause', value=value)

    @property
    def reserved(self):
        return self._gate.reserved.copy()

    @property
    def seen(self):
        return frozenset(self._gate.seen)

    @property
    def exits_pending(self):
        return frozenset(self._gate.exits_pending)

    @property
    def peak_reserved(self):
        return self._gate.peak_reserved

    @property
    def audit(self):
        return [json.loads(row[0]) for row in self.db.execute(
            "SELECT payload FROM admission_audit WHERE action='request' ORDER BY id")]

    def request(self, account, event, now, notional, *, exit=False):
        return self._change('request', account=account, event=event, now=now, notional=notional, exit=exit)

    def confirm_flat(self, account):
        if self.reconciliation_required:
            raise ValueError('Restart reconciliation required; no automatic release')
        self._change('flat', account=account)

    def _change(self, action, **kwargs):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            policy, state = self.db.execute('SELECT policy,state FROM admission WHERE id=1').fetchone()
            if policy != POLICY:
                raise ValueError('Journal policy mismatch')
            candidate = decode(json.loads(state))
            candidate.last = self.last.copy()
            result = None
            if action == 'request':
                if self.reconciliation_required:
                    result = False
                    payload = dict(account=kwargs['account'], event=kwargs['event'],
                                   reason='restart_reconciliation_required', exit=kwargs['exit'],
                                   reserved=str(sum(candidate.reserved.values(), D(0))))
                else:
                    result = candidate.request(**kwargs)
                    payload = candidate.audit[-1]
            elif action == 'pause':
                candidate.paused = kwargs['value']
                payload = {'paused': candidate.paused}
            elif action == 'flat':
                candidate.confirm_flat(kwargs['account'])
                payload = {'account': kwargs['account']}
            else:
                raise ValueError('Unknown journal operation')
            self.db.execute('UPDATE admission SET state=? WHERE id=1', (json.dumps(encode(candidate)),))
            self.db.execute('INSERT INTO admission_audit(action,payload) VALUES(?,?)', (action, json.dumps(payload)))
            self.db.execute('COMMIT')
            self._gate = candidate
            return result
        except BaseException:
            try:
                self.db.execute('ROLLBACK')
            except sqlite3.Error:
                self.close()
            raise

    def close(self):
        if self.db is not None:
            self.db.close()
            self.db = None
        if not self._lock.closed:
            self._lock.close()
