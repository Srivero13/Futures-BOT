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
