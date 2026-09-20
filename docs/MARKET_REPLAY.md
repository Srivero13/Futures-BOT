# Offline capture verification and replay

`replay_market.py` verifies the recorder manifest, file sizes and SHA-256 hashes,
then streams the saved records into a snapshot-bounded Decimal order book.
It independently checks depth continuity and reconciles event counters with the
recorder summary. Updates replace quantities; zero quantities delete levels.
Locked or crossed reconstructed books cause failure. Corrupt or truncated inputs
produce no completed report. Existing outputs are not overwritten.

```bash
python replay_market.py --capture data/YOUR-CAPTURE \
  --output data/YOUR-CAPTURE/replay-report.json
```

Every recording starts independently. A session start or recorded connection
error clears the book; depth processing requires a snapshot. Stale updates are
ignored. A recorded gap invalidates the book until a fresh session snapshot.
No book state is carried between recordings or disconnected sessions.

Only bids at or above the initial snapshot's lowest bid and asks at or below its
highest ask are retained. This avoids treating unknown deeper liquidity as a
complete book. If either covered side empties, the quote is counted as uncovered.
New levels inside these boundaries remain supported. A 200,000-level cap per
side bounds malformed or exceptionally large reconstructions.

The report includes covered/uncovered quote counts, event-weighted spread
statistics, best-level quantity imbalance, and the maximum receipt gap between
linked depth updates within each session. These are data-quality descriptions,
not trading signals, time-weighted statistics, fill estimates or latency RTT.

Price-level updates follow the official
[Binance depth-stream procedure](https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md#how-to-manage-a-local-order-book-correctly).
Passing internal checks does not prove exchange authenticity, complete historical
coverage, executable liquidity, or profitability. No model is trained or approved.

Format-version-2 `snapshot_refresh` records replace the book within the same
connection session and reset the receipt-gap calculation. Their sequence must
not regress. Each refresh starts a separate snapshot coverage epoch. Reports
include `covered_depth_fraction` (event-weighted) and `snapshot_epochs` with
covered/uncovered counts. Any future training labels must stay inside a valid
continuous coverage segment and must not cross refresh boundaries.
