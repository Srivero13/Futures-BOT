# Futures-BOT 1.5 — research and paper trading

A CPU-based Binance spot research engine with two virtual accounts, Decimal accounting, a calibrated model interface, and a supervised WebSocket coordinator. **No real orders are sent. No profitable strategy has been demonstrated.**

Version 1.5 adds bounded-memory training, resumable Binance/Coinbase data adapters, stable streaming QR fitting, optional compiled CPU inference, and cached live forecasts. All new models remain unapproved.

Read the [1.5 setup and large-data guide](docs/V1.5.md), [release results](reports/v1.5/RELEASE.md), and [operations guide](docs/OPERATIONS.md). Previous [1.1 research](reports/v1.1/RELEASE.md) remains available.

## Measured changes from 1.1

| Workload | v1.1 | v1.5 | Speedup |
|---|---:|---:|---:|
| 100,000 predictions, warmed compiled batch | 670.09 ms | 0.918 ms | 729.8× |
| 100,000 quote decisions within the same candle | 724.30 ms | 43.73 ms | 16.6× |
| 100,000 predictions, NumPy-only batch | 686.75 ms | 9.77 ms | 70.3× |

These are CPU microbenchmarks on synthetic feature vectors in the development environment. They exclude data preparation, accounting, network, and order execution. **The whole bot has not been demonstrated to be 200× faster.** The optional compiled batch path exceeds that target for the measured workload. Numerical prediction differences were below 1e-10 bps.

Training processed 527,040 existing Binance candles with a larger chronological fitting window and about 36 MiB peak RSS per process. A 30+ GB run and fresh Coinbase acquisition were not completed: public downloads timed out here. The new pipeline processes files in chunks, and the guide provides commands for larger datasets and additional venues. Historical forecasts did not beat a zero-return baseline. There are 82 automated tests.

## Requirements

| Component | Suggested minimum | Recommended for larger research |
|---|---|---|
| CPU | 64-bit x86, 2 cores | 4+ cores |
| System RAM | 4 GB | 8–16 GB |
| Free project storage, excluding OS | 5 GB | SSD with 100 GB for a 30 GB corpus and working space |
| GPU | Not required | Not required |
| Software | Ubuntu 24.04 LTS, Python 3.12, Git | Same; optional Numba for compiled batch inference |
| Network | Stable HTTPS/WebSocket access and synchronized clock | Wired connection, locally measured latency |

These are planning budgets, not certified hardware minima. See the [full requirements and platform matrix](docs/REQUIREMENTS.md), including untested platforms and data compatibility.

## Quick start

Install Ubuntu 24.04 LTS Desktop or Server using its standard installer, preserving any existing data that must be retained. Open a terminal and run:

```bash
sudo apt update
sudo apt install -y git
mkdir -p ~/projects
cd ~/projects
git clone --branch develop https://github.com/Srivero13/Futures-BOT.git
cd Futures-BOT
bash scripts/bootstrap.sh
source .venv/bin/activate
```

The setup script installs packages and runs tests; it does not start a service. See the [operations guide](docs/OPERATIONS.md) for OS settings, updates, backups, and the optional observer service. Windows code paths exist but were not validated here.

## Observe and measure

```bash
python -m engine_v1.stream --seconds 60 --output data/stream-local.json
python -m engine_v1.latency --samples 100 --location user-pc --output data/latency-local.json
python -m engine_v1.operations status --file data/observe-health.json
```

No API keys are required. The observer works without models or a portfolio database. Local profiles expire after 24 hours; eligibility is recomputed from raw timing samples. REST RTT and WebSocket interarrival are not order-execution latency. The runtime host must remain awake and its clock synchronized.

## Two virtual accounts

```bash
python -m engine_v1.stream --paper --profile data/latency-local.json --seconds 3600
python -m engine_v1.operations status
```

Default configuration: `configs/v11-paper.json`, two 1,000 USDT virtual ledgers, 100 USDT per entry, and a shared entry exposure cap of 200. Fees, slippage, and risk limits are assumptions. Only one coordinator may own the database. A valid local profile, approved recent model, closed-candle warmup, fresh quotes, and a stable clock are required for entry.

**The included models are historical and unapproved, so they do not open positions.** The rolling experiment does not automatically replace them. There is no current retraining or promotion daemon.

Operator controls in the repository directory:

```bash
touch PAUSE       # Block entries; risk and horizon exits continue on fresh quotes.
rm PAUSE          # Remove the operator pause.
touch FLATTEN     # Request virtual exits and block entries until removed.
```

Ctrl+C stops without liquidation. `FLATTEN` cannot liquidate a position without a valid quote. A stale held symbol blocks all entries but permits exits on other fresh symbols. See the guide before running unattended.

## Upgrade and preserve data

Stop the old coordinator and update with `git pull --ff-only origin develop`. Install requirements and run tests again. Version 1.5 continues using the 1.1 database at `data/v11-paper.sqlite3`, preserving existing 1.1 balances. Version 1.0 ledgers at `data/v1-paper.sqlite3` are not migrated; a separate 1.1/1.5 ledger starts with independent virtual balances. Back up a running compatible ledger with:

```bash
python -m engine_v1.operations backup data/v11-paper.sqlite3 data/backups/first.sqlite3
```

The destination must be new. Financial configuration changes still require a separate database; refreshing a transient quote deadline does not reset balances. Trade history is retained, idle events are omitted, and old deduplication rows are pruned with timestamp replay protection.

## Train and benchmark v1.5

Install the optional compiled backend and run the local benchmark:

```bash
python -m pip install -r requirements-fast.txt
python benchmark_v15.py --compiled --output data/benchmark-v15-local.json
```

Acquire a research dataset and train with explicit chronological boundaries:

```bash
python download_v15_data.py --source binance --symbol BTCUSDT \
  --start 2025-04-01 --end 2025-10-01 --root data/market
python train_v15.py --venue binance --symbol BTCUSDT \
  --files data/market/binance-BTCUSDT-*.csv \
  --train-end 2025-09-08 --calibration-end 2025-09-15 --test-end 2025-10-01 \
  --output data/research-v15 --compiled
```

The [training guide](docs/V1.5.md) covers Coinbase, multiple instruments, local imports, resumable downloads, and datasets larger than RAM. These historical dates reproduce the release's retrospective window; they are not current trading signals. Research output does not replace active models. Raw datasets stay outside Git. Archived [1.1 research](reports/v1.1/RELEASE.md) retains its original reproduction commands and results.

## Remaining scope

This is spot-only, long-only paper research. No futures, funding, margin, real/testnet execution, broker reconciliation, partial fills, queue simulation, or authenticated accounts are implemented. Capital.com and Hapi are not integrated into the new engine. One-minute candles cannot validate subsecond execution. BookTicker lacks an exchange event timestamp, and a receipt-age check cannot establish source freshness. Continuous unattended operation must be validated on each deployment host and connection.

Archived release documentation: [v1.0](docs/V1.0.md) and [v0.2](docs/V0.2.md). Their scope statements apply to those releases. The `engine_v1` package name is retained for command compatibility; its current version is 1.5.0.

## Project language

All new documentation, comments, user-facing messages, and commit messages must be written in English.

## License and contributions

This project is distributed under the [MIT License](LICENSE). See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, tests, and reproducible performance reports.
