# Bounded USD-M data expansion

Status: acquisition and alignment only, unapproved. Following the operator's
successful August 1 pilot and audit, acquire August 2–7, 2026. The end date is
exclusive. This adds six days (8,640 minutes); it does not train or select a model.

```bash
python -u batch_usdm_pilot.py \
  --symbol ETHUSDT \
  --start 2026-08-02 --end 2026-08-08 \
  --reserve-from 2026-09-01 \
  --spot-root data/market-expanded \
  --output-dir data/usdm-aug02-07
```

The output directory must be new. No existing pilot is overwritten or downloaded
again. Each day retains its archive, checksum, converted CSV and provenance.
Each day must pass the saved-pilot audit before another day is downloaded.
The batch accepts at most seven consecutive days, with every day strictly before
the reserve and current UTC date. Missing monthly spot shards fail preflight.
Per-day archive/expanded limits and disk reserve are inherited from the pilot.

`status.json` records active and completed days, audit hashes, and a status of
running, complete, failed or interrupted. Completion requires a final recheck
of report and input hashes. Ctrl+C preserves completed artifacts and records an
interruption when storage is available. Abrupt process termination or power loss
can leave a running status; that status is not evidence of a complete dataset.
There is no automatic resume. Preserve failed output for diagnosis.

Progress is emitted at day/download/audit boundaries. Socket timeout and retry
behavior comes from the existing downloader; no total wall-clock completion
guarantee is made. The batch does not require a GPU or private API credentials.

Tests cover complete batches, first-audit failure, interruption after a verified
day, invalid ranges, missing local inputs, refusal to overwrite, and changed
inputs at final verification. Batch tests mock acquisition; actual network/data
results must come from the operator's run. The existing pilot/audit tests cover
synthetic archive conversion and corruption.

These are trade-price candles. Funding, mark prices, contract rules, execution
costs and a distinct written strategy protocol remain prerequisites to futures
backtesting. More downloaded days are not evidence of improved profitability.
