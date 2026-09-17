# Join audit: trade flow and candles

After the one-day downloader pilot, verify that derived flow summaries align with
the established OHLCV corpus before building any model features:

```bash
python audit_tradeflow.py \
  --flow-files data/tradeflow-pilot/ETHUSDT-aggTrades-2026-08-01-flow.csv \
  --candle-files data/market-expanded/binance-ETHUSDT-2026-08.csv \
  --symbol ETHUSDT \
  --reserve-from 2026-09-01 \
  --output data/eth-tradeflow-alignment.json
```

The audit uses the existing Python requirements, no network and no GPU. It
rechecks the retained ZIP, derived CSV, sidecar and candle checksums, identities
and reservation boundaries. At most 31 daily flow files can be joined per run.
A flow minute must be available at exactly its closing boundary; it cannot be
used as a feature at the start of that minute. Live receipt delay remains unknown.

Checks compare first aggregate-trade price against candle open, last price against
close, and summed taker buy/sell base quantity against volume. Prices must match
exactly; flow endpoints must fall within candle high/low. This does not check
all intraminute high/low values. Volume is evaluated with Decimal arithmetic;
exact mismatches are reported even if within the fixed tolerance of 1e-8 base
units plus 1e-10 times candle volume. No thresholds are fitted to results.

The summary reports matching-minute counts, missing flow/candle minutes, price
and volume discrepancies, and the largest absolute volume discrepancy. Limited
mismatch examples appear in the JSON. Missing flow minutes are not fabricated;
an empty minute may be legitimate but prevents a full-coverage pass. Extra candle
minutes outside the requested flow days are ignored in join statistics. Duplicate
or malformed timestamps, checksum failures and premature flow availability stop
the audit without publishing a completed report.

Exit code 0 means full coverage with matching prices and volumes within tolerance;
1 publishes a completed mismatch report; 2 means an input or runtime failure.
Existing output files cannot be overwritten. No source data or models are changed.

`alignment_passed` means only that this join passed these checks. It is not data
authentication, predictive validation or model promotion; `approved` remains false.
If the pilot passes, expand a predefined development period before assessing any
new trade-flow feature. September remains reserved.
