# Public spot/USD-M quote capture pilot

This observation-only command records ETHUSDT best bid/ask prices and sizes from
two public WebSocket connections. It uses no API credentials and sends no orders.
Run a 60-second connectivity pilot before considering a longer capture:

```bash
.venv/bin/python -u record_basis_quotes.py \
  --symbol ETHUSDT --seconds 60 --max-mib 64 \
  --output-dir "data/basis-quotes-$(date -u +%Y%m%dT%H%M%SZ)"
```

The command prints progress every five seconds and a final summary. A new output
directory is mandatory. Duration is limited to 1–600 seconds, bytes to 1–1024 MiB,
with a 1 GiB free-space reserve. No training, fee assumptions or P&L is performed.
The pilot deliberately does not reconnect or fill gaps. Any feed failure,
nonincreasing update ID, invalid quote or queue overflow stops collection. A
summary with `capture_completed: false` exits nonzero; preserve its partial files.
This is not an unattended overnight collector.

## Interpretation and storage

`protocol.json` records endpoints, symbol, local freshness limit and code hashes.
Numbered JSONL parts contain validated quote fields and receipt-pair records;
`summary.json` contains counts, stop reason, byte lengths and SHA-256 hashes.
Update IDs need not be contiguous: this is best-quote capture, not depth replay.

A pair uses the latest quote from each connection only when both receipts are
at most 250 milliseconds old at pairing. Queue wait is included in this age.
Monotonic receipt timestamps define freshness and skew; wall timestamps are
recorded but not used for pairing. A pair can reuse its opposite-market quote,
so pairs are not independent observations. All valid consumed quotes are saved,
including those that cannot form a fresh pair. Pending queue contents at shutdown
are not drained and capture completeness refers only to normal pilot termination
with at least one pair, not complete exchange coverage.

Local arrival-time matching is not exchange-time synchronization. Spot bookTicker
does not supply a source event timestamp. Network asymmetry and socket buffering
can leave an apparently fresh pair economically stale. Best-level size is only
an observation, not a fill guarantee. There is no order latency, legging, depth,
fees, financing, funding or liquidation model.

Socket connection/read timeouts and bounded thread joins limit routine shutdown;
a daemon reader still blocked after the join is reported as a shutdown failure.
The tool cannot guarantee cleanup after OS failure or power loss. Buffered writes
are flushed every five seconds, not fsynced per event; abrupt termination can leave
incomplete data or a missing summary. Wall-clock jumps are not corrected.

## Sources checked 2026-10-14 UTC

- [Binance Spot WebSocket streams](https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md)
- [USD-M public book-ticker streams](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/public)

The USD-M connection uses `/public/ws/{symbol}@bookTicker`; spot uses
`stream.binance.com:9443/ws/{symbol}@bookTicker`. Endpoint availability still must
be tested from the operator's connection. Offline tests use synthetic quotes and
mock connections; they do not certify exchange reachability.

## Offline replay audit

After a normally completed capture, verify the saved files without opening any
network connections:

```bash
.venv/bin/python -u audit_basis_quotes.py \
  --capture data/basis-quotes-TIMESTAMP \
  --output data/basis-quotes-TIMESTAMP/replay-audit.json
```

Replace TIMESTAMP with the capture directory's timestamp. The output must be new.
The audit checks part names, sizes and hashes, validates normalized quotes and
per-feed ordering, reconstructs each pair from the latest saved quotes, and
reconciles record counts. It checks input hashes again after replay. It reports
receipt ages, receipt skew and how many pairs reuse each venue's quote from the
previous pair. These reuse counts are not an effective independent sample size.

The audit accepts only completed, error-free pilots. It does not certify source
completeness, exchange synchronization, executable prices or profitability. It
reuses recorder validators, so it is not an independent parser implementation.
Unpaired updates have no saved pairing-attempt timestamp; their rejection reason
cannot be independently reconstructed. A passing audit therefore validates saved
pairs, not every decision the recorder made about omitted pairs.

Synthetic tests cover correct replay and rejection of hash damage, inconsistent
rehashed pair ages and embedded quotes, stale pairs, duplicate pairs, count
mismatches and unexpected part paths. Operator captures are audited separately.

## Queue pressure and writer overhead

`Full` in a feed error means the shared 4096-record queue overflowed. It does not
identify a network outage. The capture fails and the chained audit is skipped;
keep the partial folder and use a new folder for a retry. The queue limit and
250 ms freshness rule are unchanged; no quotes are silently dropped to recover.

The quote-specific writer probes free disk space before its first write and
before another 1 MiB would be written since the previous probe. It subtracts all
intervening bytes from the cached free-space value and probes again near the
1 GiB reserve. This removes a filesystem probe from every record. Other processes
can consume disk space between probes; this reserve is not a disk reservation.
Write errors still stop the capture. Rotation, hashes and per-record byte limits
remain in effect. The existing market recorder is unchanged.

Progress includes current queue occupancy. The summary includes the observed
queue high-water mark (sampling can miss the actual peak), maximum queue wait for
consumed quotes, and an explicit overflow flag. Queue wait is measured from the
application receipt timestamp and does not measure network latency. A synthetic
10,000-record test checks preservation, rotation, hashes and reduced probe calls;
it does not certify live throughput on the operator's machine.

## Descriptive bid/ask basis

Run `describe_basis_quotes.py --capture CAPTURE --output CAPTURE/basis-description.json`
after capture. It reruns the integrity/replay audit before reading the saved pairs
and checks source hashes again afterward. Output paths must be new.

Sampling is fixed: first valid recorded pair in each one-second bucket relative
to the first pair. Subsequent pairs in that bucket are ignored, without looking
at their prices. Missing buckets are not filled. This limits event-rate weighting
but does not establish statistical independence. Coverage spans first to last
pair only; it does not measure start/end periods without valid pairs.

Metrics are 10,000 times natural log ratios:

- Midpoint basis: futures midpoint / spot midpoint.
- Lower bid/ask basis: futures bid / spot ask.
- Upper bid/ask basis: futures ask / spot bid.
- Each market's spread: ask / bid.

Means and nearest-rank 5th, 50th and 95th percentiles summarize sampled levels.
Lower and upper basis are price observations for different sides, not profits
from an opening and closing trade. Even positive differences do not establish
executable arbitrage: asynchronous receipts, fills, depth, fees, funding,
borrowing, inventory and legging remain unmodeled. No thresholds are fitted,
trades selected or model approved. This pilot is descriptive development data.
