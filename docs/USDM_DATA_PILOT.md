# USD-M futures data pilot

Status: data acquisition only, unapproved. RR-01 remains closed. This pilot does
not apply spot strategies to futures or assume that different fees rescue them.

The initial scope is ETHUSDT, August 1, 2026 UTC, one-minute trade-price candles.
September and later dates remain outside this pilot's default reserve boundary.
No API key, GPU, account access or order placement is involved.

```bash
cd ~/projects/Futures-BOT
source .venv/bin/activate
git pull --ff-only origin develop &&
python -m unittest discover -s tests -p 'test_usdm_pilot.py' -v &&
python -u download_usdm_pilot.py \
  --symbol ETHUSDT \
  --date 2026-08-01 \
  --reserve-from 2026-09-01 \
  --output-dir data/usdm-pilot-20260801
```

The output directory must not already exist. Preserve successful results; use a
new path for an intentional repeat. Failed acquisition does not publish a dataset.
The parent directory and a writer lock file may remain after failure.

## Validation and provenance

The downloader retains the source ZIP and CHECKSUM, verifies SHA-256 and the
expected archive/member names, and bounds compressed and expanded content to
8 MiB each. It requires exactly 1,440 ordered candles covering the UTC day,
strict millisecond opening/closing timestamps, and finite, consistent OHLCV.
A recognized full header or headerless rows are accepted; unknown schemas fail.
Converted timestamps are integer seconds. Decimal price strings are preserved.

The sidecar records archive/output/checksum/runner hashes, source URL, retrieval
time, requested symbol/day and `venue=binance_usdm`, `market=usd_m_futures`.
Existing spot provenance checks requiring `venue=binance` must reject this data.
Do not rename metadata to make it pass a spot backtest. A checksum verifies a
particular downloaded archive, not the economic completeness of exchange data.
Archives may subsequently be revised upstream.

Publication stages all files together and uses the project's cooperating writer
lock. This is not a power-loss durability guarantee or protection from unrelated
programs changing the output directory concurrently.

## Required before futures strategy evaluation

A successful pilot establishes only ingestion compatibility for that day.
A separate futures research protocol must define funding cash flows, mark-price
valuation, historical contract constraints, applicable fees, spread/slippage,
position accounting, and an execution model. Missing inputs must be reported,
not silently replaced with spot assumptions. No leverage or live trading is
configured here. Broader downloads and model training are outside this pilot.

## Sources and verification scope

- [Binance public-data documentation](https://github.com/binance/binance-public-data)
  documents USD-M klines separately from spot data and supplies archive checksums.
- Archive namespace: `data/futures/um/daily/klines/ETHUSDT/1m/` on
  `https://data.binance.vision/`.

Unit tests use synthetic archives and mocked downloads. They cover complete
header/headerless days, invalid data/checksums, output isolation, reserve-date
rejection and failed-download cleanup. A successful public archive download on
the operator's machine is still needed; no live archive result is claimed.
