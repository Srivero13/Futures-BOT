# Stream failure handling

The observe/paper stream distinguishes feed failures from local persistence
failures. Network exceptions still clear quotes and retry with bounded backoff.

An operating-system, SQLite, or validation error during a paper transaction,
ledger pruning, or health-file write instead raises `LocalRuntimeError`. It
stops the run, closes the active socket, and closes an initialized paper ledger.
The original exception is retained as its cause for diagnosis. Reconnecting
cannot repair a full disk, unavailable database, or invalid ledger event.

A final stopped-health write is attempted during cleanup. If storage itself is
unavailable, this write may also fail and the previous health file may remain
stale. Do not interpret an old `running: true` value as proof of a live process.
No automatic recovery, database repair, or live order submission is introduced.

Run offline regression checks:

```bash
python -m unittest discover -s tests -p 'test_runtime_errors.py' -v
```

## Interrupted paper transactions

Paper transactions now roll back on interrupts as well as ordinary exceptions.
An interruption after updating the first account must roll back all account,
risk, event, and deduplication writes in that transaction. If rollback itself
fails, the connection is closed and the original error is retained with a
cleanup note; the connection must not be reused.

Fault-injection tests reopen a real temporary SQLite ledger, retry the failed
event, reopen it again, and verify that replaying the committed event does not
duplicate trades:

```bash
python -m unittest discover -s tests -p 'test_ledger_recovery.py' -v
```

These tests cover application interrupts and simulated write/commit failures.
They do not certify recovery from hardware faults, filesystem corruption, or
power loss. A failure before commit is tested; an ambiguous error after a commit
still requires inspecting the persisted ledger before retrying with a new ID.

## Abrupt process termination

A separate subprocess test now kills a test-owned worker at three checkpoints:

| Checkpoint | Expected state after reopening |
| --- | --- |
| First account updated, transaction open | No account, risk, audit, or deduplication changes |
| All transaction writes finished, before commit | No pending writes survive |
| Commit returned, before acknowledging completion | Both trades and their deduplication records survive |

Each case runs SQLite's integrity check, compares recovered account/risk state
with a clean or committed reference ledger, and retries the same event ID.
The retry must create exactly two trades for an uncommitted event, or no new
trades for an already committed event.

Run this offline on the filesystem used for the bot:

```bash
python -m unittest discover -s tests -p 'test_ledger_process_crash.py' -v
```

The test uses disposable ledgers in the system temporary directory and kills
only its own child process. To test the filesystem containing the project data
on Linux, choose a temporary directory there:

```bash
mkdir -p data/recovery-test-tmp
TMPDIR="$PWD/data/recovery-test-tmp" python -m unittest discover -s tests -p 'test_ledger_process_crash.py' -v
```

No existing bot process or ledger is accessed. A process kill leaves the OS and
storage running; this is not a power-loss or disk-failure test. The checkpoints
surround commit rather than interrupting SQLite inside commit. Event-ID
deduplication is tested while those records are retained; this is not an
exchange-side exactly-once guarantee.
