# Futures-BOT 1.1 — research and paper trading

A CPU-based Binance spot research engine with two virtual accounts, Decimal accounting, a calibrated model interface, and a supervised WebSocket coordinator. **No real orders are sent. No profitable strategy has been demonstrated.**

Version 1.1 fixes stale-feed exit blocking, bounds telemetry, reduces idle database growth, adds operator controls and backups, and expands validation to rolling historical periods. It includes an optional volatility-scaled Ridge model. The historical models remain unapproved; installing this release does not enable trading.

Read the [1.1 audit and research report](reports/v1.1/RELEASE.md), [operations guide](docs/OPERATIONS.md), [locked experiment protocol](reports/v1.1/PROTOCOL.json), [evaluation](reports/v1.1/evaluation.json), and [engineering benchmark](reports/v1.1/benchmark.json).

## Measured changes

| Measure | v1.0 | v1.1 |
|---|---:|---:|
| Median feature calculation, same 10,000 candles | 132.61 ms | 6.38 ms |
| Database after 10,000 idle ticks | 3,252,224 bytes | 491,520 bytes |
| Idle audit rows in that workload | 10,000 | 0 |
| Recent timing samples retained | Unbounded | 4,096 per series |
| Unique automated tests | 43 | 65 |

Feature computation was approximately 20.8× faster. The idle ledger workload itself took 0.540 s versus 0.565 s, so not every path became faster. Figures describe the development environment, not the dedicated i7 PC or Binance execution. Numerical feature equivalence was checked within tolerance. Trade audit rows remain retained.

## Install on the dedicated PC

Use Ubuntu Desktop 24.04 LTS and Python 3.12. The i7-9700F, 16 GB RAM, RX 570, and SSD are sufficient for this workload; GPU acceleration is not required.

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

No API keys are required. The observer works without models or a portfolio database. Local profiles expire after 24 hours; eligibility is recomputed from raw timing samples. REST RTT and WebSocket interarrival are not order-execution latency. The PC must remain awake and its clock synchronized.

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

Stop the old coordinator and update with `git pull --ff-only origin develop`. Install requirements and run tests again. The new database is `data/v11-paper.sqlite3`; the old `data/v1-paper.sqlite3` is preserved and is not migrated. New virtual balances start independently. Back up a running 1.1 ledger with:

```bash
python -m engine_v1.operations backup data/v11-paper.sqlite3 data/backups/first.sqlite3
```

The destination must be new. Financial configuration changes still require a separate database; refreshing a transient quote deadline does not reset balances. Trade history is retained, idle events are omitted, and old deduplication rows are pruned with timestamp replay protection.

## Reproduce research

```bash
python download_v11_data.py
python train_v11.py
python benchmark_v11.py
```

The experiment uses 527,040 official one-minute BTC/ETH candles across April–September 2025. Twelve archive checksums are verified. For each July, August, and September evaluation, the preceding 56 days are split into 28 fitting, 14 calibration, and 14 selection days. Three horizons and two Ridge variants are compared; cash is an explicit deployment alternative. Daily block-bootstrap intervals and out-of-sample error/coverage are reported.

Raw CSVs and detailed trade logs are generated locally. Concise results, hashes, and historical model artifacts are committed. The benchmark requires the original v1.0 commit in Git history. Historical results and normalized per-second averages are not income forecasts. No parameters are retuned after viewing these test months.

## Remaining scope

This is spot-only, long-only paper research. No futures, funding, margin, real/testnet execution, broker reconciliation, partial fills, queue simulation, or authenticated accounts are implemented. Capital.com and Hapi are not integrated into the new engine. One-minute candles cannot validate subsecond execution. BookTicker lacks an exchange event timestamp, and a receipt-age check cannot establish source freshness. Continuous operation on the dedicated PC and its ENTEL connection remains unverified.

Archived release documentation: [v1.0](docs/V1.0.md) and [v0.2](docs/V0.2.md). Their scope statements apply to those releases. The `engine_v1` package name is retained for command compatibility; its current version is 1.1.0.

## Project language

All new documentation, comments, user-facing messages, and commit messages must be written in English.
