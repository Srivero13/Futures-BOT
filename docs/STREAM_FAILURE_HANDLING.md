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
