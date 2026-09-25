# Futures-BOT 1.6.2 — research and paper trading

A CPU-based Binance spot research engine with two virtual accounts, Decimal accounting, a calibrated model interface, and a supervised WebSocket coordinator. **No real orders are sent. No profitable strategy has been demonstrated.**

Patch 1.6.2 treats the final deadline-bounded socket read timeout as normal session completion, avoiding a false reconnect/error at the requested end time. Earlier read timeouts and continuous-session failures still trigger recovery.

Patch 1.6.1 adds periodic observer/paper console progress, including connection state, elapsed/remaining time, message counts, receipt-fresh quotes, and errors. See [progress options](docs/START_HERE.md#console-progress).

Version 1.6 adds a 27-term nonlinear Ridge research model, a startup doctor, a guarded launcher, progress reporting, content-identified training runs, completed-fit recovery, and atomic artifacts. Existing Decimal accounting and paper risk controls remain in place. Complexity does not guarantee accuracy: the new models remain unapproved.

**New installation? Follow [Start here](docs/START_HERE.md).** See the [release audit and results](reports/v1.6/RELEASE.md), [requirements](docs/REQUIREMENTS.md), and [operations guide](docs/OPERATIONS.md).

## Release validation

The release includes failure tests for missing dependencies, insufficient data, low disk space, concurrent training, interrupted fits, evaluation recovery, modified inputs, corrupt artifacts, and failed shutdown health writes. A fresh virtual environment is checked separately. Detailed counts and results are recorded in the release report.

Both linear and nonlinear models were evaluated on the same historical periods. On jointly accepted rows, neither beat the zero-return forecast. The five-second observer probe handled a proxy failure and exited cleanly; it did not establish live feed availability. No 30+ GB run or continuous unattended test has been completed.

The [v1.5 benchmarks](reports/v1.5/RELEASE.md) remain archived. Their roughly 730× result applies to warmed compiled **linear batch inference**, not the nonlinear model or total-bot speed.

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
python doctor.py
```

The setup script installs packages and runs tests; it does not start a service. See the [operations guide](docs/OPERATIONS.md) for OS settings, updates, backups, and the optional observer service. Windows code paths exist but were not validated here.

## Observe and measure

```bash
python start_bot.py --seconds 60 --output data/stream-local.json
python -m engine_v1.latency --samples 100 --location user-pc --output data/latency-local.json
python -m engine_v1.operations status --file data/observe-health.json
```

No API keys are required. The observer works without models or a portfolio database. Local profiles expire after 24 hours; eligibility is recomputed from raw timing samples. REST RTT and WebSocket interarrival are not order-execution latency. The runtime host must remain awake and its clock synchronized.

## Two virtual accounts

```bash
python start_bot.py --paper --profile data/latency-local.json --seconds 3600
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

Stop the old coordinator and update with `git pull --ff-only origin develop`. Install requirements and run tests again. Version 1.6 continues using the 1.1 database at `data/v11-paper.sqlite3`, preserving existing 1.1 balances. Version 1.0 ledgers at `data/v1-paper.sqlite3` are not migrated; a separate 1.1/1.6 ledger starts with independent virtual balances. Back up a running compatible ledger with:

```bash
python -m engine_v1.operations backup data/v11-paper.sqlite3 data/backups/first.sqlite3
```

The destination must be new. Financial configuration changes still require a separate database; refreshing a transient quote deadline does not reset balances. Trade history is retained, idle events are omitted, and old deduplication rows are pruned with timestamp replay protection.

## Train v1.6

```bash
python download_v15_data.py --source binance --symbol BTCUSDT \
  --start 2025-04-01 --end 2025-10-01 --root data/market
python train_v16.py --venue binance --symbol BTCUSDT \
  --files data/market/binance-BTCUSDT-*.csv \
  --train-end 2025-09-08 --calibration-end 2025-09-15 --test-end 2025-10-01 \
  --model polynomial --chunk-size 4096 --output data/research-v16
```

These historical dates reproduce the release's retrospective window; they are not current trading signals. Use `--model linear` for the baseline. Both use base dependencies and require no GPU. [Start here](docs/START_HERE.md) explains output files, progress, restart behavior, and troubleshooting. Repeating a command resumes from a completed fit when available; partial fitting passes restart. Research output never replaces active models automatically.

## Remaining scope

This is spot-only, long-only paper research. No futures, funding, margin, real/testnet execution, broker reconciliation, partial fills, queue simulation, or authenticated accounts are implemented. Capital.com and Hapi are not integrated into the new engine. One-minute candles cannot validate subsecond execution. BookTicker lacks an exchange event timestamp, and a receipt-age check cannot establish source freshness. Continuous unattended operation must be validated on each deployment host and connection.

Archived release documentation: [v1.0](docs/V1.0.md) and [v0.2](docs/V0.2.md). Their scope statements apply to those releases. The `engine_v1` package name is retained for command compatibility; its current version is 1.6.2.

## Project language

All new documentation, comments, user-facing messages, and commit messages must be written in English.

## License and contributions

This project is distributed under the [MIT License](LICENSE). See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, tests, and reproducible performance reports.

### Execute historical v1.6 model signals

Use the offline [one-minute execution backtest](docs/EXECUTION_BACKTEST.md) to
measure simulated net P&L, costs, drawdown, and non-overlapping trades from an
existing model. It includes explicit whole-bar delay assumptions and never
approves a model or sends orders.

If a model produces zero trades, use the [forecast diagnostics](docs/FORECAST_DIAGNOSTICS.md)
to distinguish raw forecasts below costs from candidates blocked by the calibration
buffer. Diagnostics preserve the existing model and entry assumptions.

Use [walk-forward research](docs/WALK_FORWARD.md) to refit fixed model settings
across chronological monthly folds and evaluate forecast ranking using
calibration-defined buckets. Results remain retrospective and unapproved.

Walk-forward research also supports **15- and 60-minute horizons**, fixed momentum,
mean-reversion and zero-return forecast baselines, and `--reserve-from` to keep
specified dates outside development folds. See the [declared experiment and
reservation rules](docs/WALK_FORWARD.md#declare-development-and-reserved-dates).

Before changing features, run the [development data and feature audit](docs/DATA_FEATURE_AUDIT.md)
to inspect gaps, unusual price/volume observations, and monthly univariate feature
associations. It preserves all source data and excludes reserved dates.

The [fixed normalized-decline experiment](docs/REVERSAL_EXPERIMENT.md) tests one
calibration-defined reversal rule through the existing offline execution simulator,
with unchanged cost assumptions and no model approval or live orders.

Use [execution attribution](docs/EXECUTION_ATTRIBUTION.md) to reconcile saved
reversal trades with source candle opens and separate pre-entry movement,
holding-period gross P&L, and charged execution costs.

The [trade-flow data pilot](docs/TRADE_FLOW_DATA.md) downloads verified daily
Binance spot aggregate trades and produces closed-minute aggressive buy/sell flow
summaries with storage limits. It adds a data source, not an approved strategy
or historical order-book reconstruction.

After acquisition, run the [trade-flow alignment audit](docs/TRADE_FLOW_ALIGNMENT.md)
to compare minute availability, first/last prices and summed volume with verified
candles before building new features.

For a fixed comparison of candle-only and candle-plus-flow forecasts on verified
monthly data, see [Paired trade-flow research](docs/TRADE_FLOW_RESEARCH.md).

Optional [parallel CPU/GPU research](docs/PARALLEL_RESEARCH.md) runs fixed
polynomial and neural experiments with separate logs and no live-model approval.

Inspect completed paired experiments without retraining using
[saved research diagnostics](docs/SAVED_RESEARCH_DIAGNOSTICS.md).

[Live research capture](docs/LIVE_CAPTURE.md) records public spot trades, depth
updates and snapshots with receipt timestamps, sequence checks and storage limits.

[Offline market replay](docs/MARKET_REPLAY.md) verifies recorded-file integrity
and reconstructs each session within its initial snapshot coverage boundaries.

Build [continuous microstructure samples](docs/MICROSTRUCTURE_SAMPLES.md) from
verified recordings without allowing labels to cross coverage or snapshot gaps.

Fit a [frozen microstructure CPU model](docs/FROZEN_MICROSTRUCTURE_MODEL.md)
and evaluate it on a separate recording collected after fitting.

Inspect frozen forecasts with the [delayed-quote execution-cost diagnostic](docs/MICROSTRUCTURE_EXECUTION_COSTS.md).

Build and fit [delayed-entry quote-return models](docs/DELAYED_MICROSTRUCTURE.md)
with observed spread in the target and a separate frozen forward evaluation.

Inspect [paired block uncertainty and an imbalance-only baseline](docs/DELAYED_UNCERTAINTY.md)
from saved delayed-model datasets without changing the frozen model.

Replay [delayed-model execution with fixed cost gates](docs/DELAYED_EXECUTION.md)
to compare frozen bucket selection with modeled-cost eligibility.

Study [fixed paired holding periods](docs/HORIZON_PROFILE.md) at 5, 15, 30 and
60 seconds using unchanged frozen signals and the same completed entry samples.

Compare [causal best-quote dynamics](docs/QUOTE_DYNAMICS.md) against the three-feature
baseline on identical delayed-label samples from existing recordings.

Compare [receipt-ordered aggressive trade flow](docs/AGGRESSIVE_FLOW.md) with the
three-feature baseline using existing captures and identical delayed-label rows.

[Freeze all three feature models](docs/FROZEN_FEATURE_PACK.md) once and evaluate
them without refitting on fresh recordings across days.

[Consolidate frozen evaluations and document actual account fees](docs/PACK_SUMMARY_AND_FEES.md)
without modifying the frozen comparison pack.

Optionally [query Spot commission rates locally with read-only credentials](docs/READ_ONLY_SPOT_FEES.md).
The helper sends no orders and saves no credentials.

[Measure the frozen models' cost shortfall](docs/PACK_COST_DIAGNOSTIC.md) using
explicit fee and slippage inputs, without an API key or additional training.

Test a separate [fixed hourly trend hypothesis](docs/HOURLY_TREND.md) on development
data with delayed fills and costs, preserving the frozen microstructure models.
Its saved-trade robustness diagnostic checks best-trade concentration and adverse
slippage sensitivity without retuning the strategy.
