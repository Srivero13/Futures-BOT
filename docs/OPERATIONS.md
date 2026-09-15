# Installation and operations

Version 1.5 remains a Binance spot research and paper system. No API keys, exchange orders, leverage, or funded accounts are used. The two configured accounts are virtual ledgers.

## Host setup

Use a Linux host meeting the [system requirements](REQUIREMENTS.md). The documented setup targets Ubuntu 24.04 LTS Desktop or Server; headless operation is supported by the terminal workflow. Use a stable connection, preserve existing disk data during OS installation, disable automatic suspend during sessions, and install system updates. UTC is a convenient display timezone for logs; candle timestamps and research boundaries are UTC regardless of the host display timezone. Enable time synchronization:

```bash
sudo timedatectl set-timezone Etc/UTC
sudo timedatectl set-ntp true
timedatectl status
```

Install Git if it is missing, then clone and bootstrap:

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

The script installs dependencies and runs tests. It does not start trading or a background service. All commands below assume this repository directory and activated virtual environment. Network-dependent commands may fail if Binance is unavailable from the connection. Do not substitute synthetic prices for failed live data.

## Upgrade from an earlier release

Stop any running coordinator before updating code. Keep its database and models:

```bash
git pull --ff-only origin develop
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Version 1.5 retains the 1.1 database path `data/v11-paper.sqlite3` and its existing balances. The prior `data/v1-paper.sqlite3` is not migrated or overwritten; balances are not transferred. The new database starts with virtual capital from `configs/v11-paper.json`. An old schema passed to the new engine is rejected. Preserve an old ledger to avoid losing its open-position history.

The financial fingerprint excludes the transient quote deadline, so a refreshed latency profile can change that deadline without changing balances. Changing account identities, capital, notional, model horizon, or financial risk settings still requires a separate database. Do not delete a ledger to bypass a persistent loss halt.

## Local measurements and observation

```bash
python -m engine_v1.stream --seconds 60 --output data/stream-local.json
python -m engine_v1.latency --samples 100 --location user-pc --output data/latency-local.json
```

Observation requires no model files or portfolio database. Health is written atomically to `data/observe-health.json`. Profiles must come from the actual PC, contain raw measurements, pass endpoint thresholds, and have bounded clock uncertainty. The loader recomputes eligibility rather than trusting stored flags. Profiles expire after 24 hours. REST RTT and message interarrival are not order latency. A profile is a measurement file, not authenticated proof of its machine of origin.

## Supervised paper session

```bash
python -m engine_v1.stream --paper --profile data/latency-local.json --seconds 3600
python -m engine_v1.operations status
```

Paper health is in `data/health.json`. `--config` selects another paper configuration; `--health` selects a different health file. `--seconds 0` runs until interrupted. Only one coordinator may own a given database at a time. Separate databases do not share a global exposure limit; use the two-account coordinator for shared risk.

Health includes heartbeat age, quote ages, candle warmup, entry-gate reasons, errors, and last recorded account marks. A fresh heartbeat does not imply a healthy feed. Missing/stale quotes and gate reasons must also be inspected. A stopped process sets `running=false`; an unclean crash leaves a heartbeat that becomes stale. Error details omit response bodies and credentials.

The included historical models are unapproved. They will not open positions. Model approval, age, candle warmup, quote age, profile age, operator controls, and clock-jump checks are all required. Rolling research artifacts in `reports/v1.1/models` are not automatically installed. There is no current-data retraining or promotion daemon.

## Operator controls

Pause new entries while retaining fresh-quote risk and horizon exits:

```bash
touch PAUSE
```

Resume the entry gate:

```bash
rm PAUSE
```

Request virtual liquidation and block new entries:

```bash
touch FLATTEN
```

`FLATTEN` stays active until removed. It can only simulate exits when each position has a valid quote. It does not send exchange orders and is not a guaranteed liquidation during an outage. Remove it only when its continued effect is no longer wanted:

```bash
rm FLATTEN
```

Ctrl+C stops the coordinator without automatically liquidating. If liquidation is desired, create `FLATTEN`, verify positions have reached zero, then stop. A stale held symbol blocks all new entries but no longer blocks exits on other fresh symbols. Full paper fills remain an assumption.

## Backup and storage

Use SQLite's online backup API, not a raw copy of a live database file:

```bash
python -m engine_v1.operations backup data/v11-paper.sqlite3 data/backups/v11-first.sqlite3
```

The destination must not exist. The backup includes committed WAL contents and is integrity-checked before publication. Restore only while stopped, keeping the original files. No automatic restore or risk-state reset is performed.

Timing buffers retain the most recent 4096 samples. HOLD rows are omitted from the audit table; BUY/SELL events are retained. Deduplication rows older than one day are pruned every five minutes during paper operation, while persisted account timestamps reject older replay attempts. The finite retention applies to deduplication, not trade history: database size can still grow with actual simulated trades. Check disk space and back up periodically.

## Optional observer service

After verifying the foreground observer, install the supplied **observation-only** user service:

```bash
mkdir -p ~/.config/systemd/user
cp deploy/futures-bot-observe.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now futures-bot-observe.service
systemctl --user status futures-bot-observe.service
journalctl --user -u futures-bot-observe.service -n 50
```

Its paths assume `~/projects/Futures-BOT`; edit the service if your checkout is elsewhere. It starts with the user manager. To allow the user manager to run after logout and at boot:

```bash
sudo loginctl enable-linger "$USER"
```

Stop and disable it with:

```bash
systemctl --user disable --now futures-bot-observe.service
```

The observer maintains bounded telemetry and reconnects; it does not save a historical tick dataset. The unit is supplied as an example; systemd validation could not initialize a user manager in the development container, and host reboot behavior was not tested. No automatically trading service is enabled by this release.

## Current research workflow

See the [v1.5 acquisition and training guide](V1.5.md) for chunked datasets, Coinbase/Binance adapters, and compiled inference. Research artifacts remain unapproved.

## Archived v1.1 research commands

```bash
python download_v11_data.py
python train_v11.py
python benchmark_v11.py
```

The downloader checks 12 official monthly archives and writes validated datasets atomically. The locked experiment is `reports/v1.1/PROTOCOL.json`. Detailed trade logs regenerate locally; concise results and model artifacts are versioned. `benchmark_v11.py` requires the original v1.0 commit in Git history. These are development measurements; benchmark each deployment host and connection separately.
