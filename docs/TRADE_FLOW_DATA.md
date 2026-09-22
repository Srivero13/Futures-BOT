# Trade-flow pilot: acquisition before modeling

The candle-only ETH normalized-reversal experiment is archived as unsuccessful:
167 simulated trades across March–August 2026, zero profitable months, and a sum
of independent-month net P&L of −43.258762911322127 USDT. Reference-price holding
P&L was +0.14796291 USDT, with 33.389789083081127 USDT fees and 10.016936738241 USDT
spread/slippage. These are supplied local research results, not live executions.
Preserve the original reports; no strategy has been promoted.

The next stage acquires information missing from OHLCV: aggressive buy/sell flow
and aggregate-event activity. Acquisition does not establish predictive value.

## Verified source capabilities

[Binance's public archive documentation](https://github.com/binance/binance-public-data#spot)
documents spot daily/monthly aggregate trades, raw trades and klines, accompanying
ZIP checksums, and microsecond spot timestamps beginning January 1, 2025. Archive
files can later be revised. The downloader retains downloaded ZIPs and hashes to
identify the exact source used.

[Binance's WebSocket documentation](https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams)
describes aggregate trades and live depth updates. A trade's buyer-maker flag
identifies the resting side: buyer-maker true is classified here as an aggressive
sell; false as an aggressive buy. This is executed trade flow, not resting liquidity.

The spot archive listing inspected does not establish historical full-depth
availability. This implementation does not acquire or reconstruct an order book.
A future depth collector needs snapshot/update sequencing and resynchronization;
trade archives alone cannot supply queue position, historical spread or fill probability.

## One-day pilot

```bash
python download_tradeflow.py \
  --symbol ETHUSDT \
  --start 2026-08-01 \
  --end 2026-08-02 \
  --reserve-from 2026-09-01 \
  --root data/tradeflow-pilot \
  --max-total-gib 8 \
  --max-archive-mib 512
```

Python 3.12 with existing requirements is sufficient. No GPU, keys or account
permissions are required. The end is exclusive. Only past completed days before
the reservation are requested. At most 31 days are accepted per invocation.
Start with one day to measure actual event counts, compressed size and empty
minutes before provisioning a larger corpus. No 30+ GB requirement is assumed.

The downloader enforces a directory budget (including existing files), a 1 GiB
free-disk reserve, a per-download compressed limit, and a 4 GiB uncompressed
member limit. Archive CSVs are streamed without extraction; memory does not grow
with archive size. Transfers use 15-second socket timeouts, limited retries for
HTTP transient errors/URL failures/timeouts, and periodic byte progress. A 404
fails visibly; no synthetic replacement data is generated. The requested pilot
has not been live-download verified by the development tests.

## Artifacts and recovery

Each day produces:

- Original `SYMBOL-aggTrades-DATE.zip`, verified against the official `.CHECKSUM`.
- `SYMBOL-aggTrades-DATE-flow.csv`, with one row per observed minute.
- `SYMBOL-aggTrades-DATE.json`, written last, recording hashes, converter version,
  event/coverage statistics, byte sizes, timestamp units, source URL and symbol.

Completed days are reused only after raw/derived hashes and converter identity
pass. Interrupted transfers clean partial files; a verified raw archive can be
reprocessed after an interrupted conversion. Changed converter versions require
a new root rather than silently mixing schemas. Modified artifacts fail closed.
The root lock prevents competing downloads. All files remain local under `data/`.

## Summary schema and timing

`timestamp` is the UTC minute start in seconds. `available_at_ms` is its closing
boundary in milliseconds. Downstream features must not use that minute's summary
before this boundary; receipt delays are not measured by archives. Original
microsecond timestamps remain available in the retained raw ZIP.

Each row records aggregate-event count, trade-ID span count, taker buy/sell base
quantity and quote notional, first/last trade price, and volume/notional imbalance:
`(buy − sell) / (buy + sell)`. Aggregation uses Decimal arithmetic. The ID span
count sums `last_trade_id − first_trade_id + 1`; it is not independently verified
as the number of individual executions. Use aggregate-event count as the directly
observed activity measure. No arrival rate or RTT is inferred from minute counts.

Empty minutes are counted but not fabricated or forward-filled. Duplicate or
out-of-order aggregate IDs, decreasing timestamps, invalid fields and out-of-day
timestamps stop conversion. Gaps between aggregate IDs and maximum intertrade
gap are recorded for inspection; they do not independently prove packet loss or
missing archive data. Validation does not assume underlying trade-ID ranges are
disjoint. Repeated timestamps are allowed.

This CSV is a new schema and must not be passed to `train_v16.py` as OHLCV. The
pilot first needs a timestamp/coverage join audit against existing candles. Only
then should a separate, predeclared feature experiment use these summaries.
It changes no trading code, cost assumptions, active models, or approval state.
