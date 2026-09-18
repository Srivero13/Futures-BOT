# Live market research recorder

`record_market.py` stores Binance spot aggregate trades, 100 ms diff-depth events,
and a REST depth snapshot at each connection. It uses public endpoints only and
has no account credentials, trading client or model promotion path.

```bash
python record_market.py --symbol ETHUSDT --seconds 21600 --max-gib 4 \
  --output-dir data/live-capture-unique-name
```

The directory must be new. Default duration is six hours; the process stops earlier
at the 4 GiB event budget or 1 GiB free-space reserve. Metadata uses a small
additional amount of space. Files rotate at approximately 64 MiB and contain
JSON Lines with exchange payloads, session IDs, application receipt wall-clock
nanoseconds and monotonic nanoseconds. Progress prints about every ten seconds
while messages arrive. No existing data are overwritten or deleted.

A WebSocket connects before the REST snapshot request. Frames received while
fetching the snapshot remain in the socket buffer: their recorded receipt time is
when Python reads them, not physical arrival time. Exchange event timestamps
remain in milliseconds. Wall-clock changes above 100 ms relative to monotonic
time are flagged; no NTP offset correction or network latency estimate is made.

Depth ranges at or below the snapshot sequence are marked stale. A range must
cover the next expected sequence; a gap is recorded and starts a fresh connection
and snapshot. Sequence checks follow the official
[Binance stream documentation](https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md#how-to-manage-a-local-order-book-correctly).
The recorder does not reconstruct price levels or certify an executable book.
Snapshots cover at most 1000 levels per side. The saved snapshots and events can
support a separate replay implementation, subject to these coverage limits.

Aggregate trade ID gaps and stale IDs are counted across sessions. Disconnect
intervals are not backfilled. Silence longer than 30 seconds triggers reconnect;
retry delay increases to 32 seconds, and ten consecutive failed sessions stop the
run. Ctrl+C writes a final summary. Network calls can extend shutdown by several
seconds. A hard kill or power failure can leave the last line incomplete and no
final manifest. Files flush during progress; this is not a durable packet recorder.

The final `summary.json` includes errors, stop reason, counts and file SHA-256
hashes. Review these before treating a recording as usable data. A duration stop
alone does not certify continuous coverage or synchronized depth.

These newly collected September data are explicitly prospective development data,
not an untouched holdout for the earlier experiments. The historical training
commands retain their September boundary. No profitability claim follows from
collecting more detailed data.
