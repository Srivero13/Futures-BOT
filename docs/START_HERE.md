# Start here: Futures-BOT 1.6

This guide installs a CPU-based research environment, checks it, observes public prices, and trains a model. No API keys or funded exchange accounts are needed. The included engine sends no real orders. A successful training run is not approval to trade.

## 1. Install the operating system and project

Use Ubuntu 24.04 LTS Desktop or Server with Python 3.12. See the [public requirements](REQUIREMENTS.md) for hardware planning. Preserve any existing files before installing an OS. Apply system updates, keep the system clock synchronized, and disable suspend during long sessions.

Open a terminal:

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

For an existing checkout, stop its running processes first, then use:

```bash
git pull --ff-only origin develop
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python doctor.py
```

The base requirements pin NumPy 2.3.5 and websocket-client 1.8.0. The new nonlinear trainer uses these base dependencies; Numba and a GPU are optional and unnecessary for this workflow. The doctor checks the Python/dependency versions, writable output disk with a 1 GiB reserve, feature computation, included model integrity, and an in-memory paper ledger. Its `ready` result covers these offline checks only.

## 2. Observe before starting a long session

```bash
python start_bot.py --seconds 60 --output data/first-observation.json
python -m engine_v1.operations status --file data/observe-health.json
```

`start_bot.py` runs the doctor before starting the existing observer/paper coordinator. Inspect the message count, connection errors, quote ages, and heartbeat. A running process with zero messages does not establish working market access. If the feed works, `--seconds 0` keeps observation running until Ctrl+C. The [operations guide](OPERATIONS.md) covers optional services, backups, and paper controls.

The release workspace's five-second network probe encountered a WebSocket proxy error, recorded the failure, and shut down normally. Successful live access and 24/7 behavior on other hosts were not demonstrated by that probe. Test the actual network before leaving a session running.

## 3. Download training data

This small historical example reproduces the release's date window:

```bash
python download_v15_data.py --source binance --symbol BTCUSDT \
  --start 2025-04-01 --end 2025-10-01 --root data/market
```

The downloader name remains `download_v15_data.py` for compatibility. Completed monthly shards are checksum-verified and reused when the command is repeated. If public downloads are blocked or time out, resolve access first; the trainer does not fabricate replacement data. For Coinbase, larger histories, or local CSV/gzip imports, see the [data guide](V1.5.md). Train each venue/symbol separately.

The example dates are retrospective, not a current trading signal. New research should use completed periods, fix its train/calibration/test boundaries before viewing results, and reserve later data for evaluation. Increasing dataset size alone does not establish quality or predictive value.

## 4. Train the nonlinear model

```bash
python train_v16.py --venue binance --symbol BTCUSDT \
  --files data/market/binance-BTCUSDT-*.csv \
  --train-end 2025-09-08 --calibration-end 2025-09-15 --test-end 2025-10-01 \
  --model polynomial --horizon 3 --alpha 10 --chunk-size 4096 \
  --output data/research-v16
```

This expands the six causal inputs into 27 terms: the original features, their squares, and pairwise interactions. Training-only scaling, Ridge regularization, streaming QR, a separate error-calibration interval, and out-of-distribution rejection are retained. It models nonlinear relationships without a deep-learning framework. More flexibility also creates overfitting risk; the release comparison did not establish an edge.

Progress shows data validation, moments, QR, calibration, and evaluation. Initial file hashing can take time on large inputs before progress starts. The default chunk size is 4,096; reduce it toward 512 if memory is constrained. Supported horizons are 1, 3, and 5 minutes. Keep chosen parameters fixed before evaluating a reserved test interval.

Run the same command with `--model linear` for the simpler baseline. The outputs occupy distinct run directories. Repeat acquisition/training with ETHUSDT for a separate Ethereum model. The trainer does not use Numba, so installing `requirements-fast.txt` is not necessary for these commands.

## 5. Read the output and recover from interruptions

Each content-identified run directory contains:

| File | Meaning |
|---|---|
| `spec.json` | Input hashes, software/algorithm identity, source information, and fixed parameters |
| `status.json` | Latest state, stage, count, timestamp, or failure message |
| `model.json` | Checksummed, atomically saved research model |
| `fit-complete.json` | Verified completed fit and calibration checkpoint |
| `evaluation.json` | Holdout diagnostics; P&L remains null |
| `complete.json` | Final model/report hashes, written only after successful evaluation |

Only treat a run as completed when `complete.json` exists and the same training command verifies it. Repeating an identical completed run validates and returns its artifacts. After an evaluation failure, repeating the command reuses the completed fit. If interrupted during validation, moments, QR, or calibration, those fitting stages restart: partial QR progress is not checkpointed. A hard power loss may leave a stale `running` status; the process lock is released by the OS, and rerunning recovers according to the available checkpoint.

Different inputs, parameters, NumPy/Python versions, or algorithm/runner hashes create a new directory. Concurrent processes cannot mutate the same run. Different runs can still consume resources simultaneously; start with one training job. Corrupted checkpoints fail integrity checks rather than silently retraining over existing artifacts. Input files must remain unchanged during a run.

No research model is copied to the active `models/` directory or approved automatically. The release models failed to beat a zero-return baseline. Do not edit approval flags or timestamps merely to bypass those checks.

## Troubleshooting

| Symptom | Action |
|---|---|
| Missing module or version mismatch | Activate `.venv`, then run `python -m pip install -r requirements.txt` and `python doctor.py` |
| Dataset not found or literal `*.csv` in the error | Finish downloading and verify the files match the command's path |
| Insufficient fit/calibration/test examples | Check UTC boundaries, timeframe, missing minutes, and coverage; minimum example counts are 100/30/30 |
| Input overlap or integrity mismatch | Inspect shard order, duplicate files, and checksums; preserve the original evidence before correcting data |
| Output disk below reserve | Free space or choose another `--output` directory; maintain additional space for the OS and data |
| Memory pressure | Run one job and reduce `--chunk-size`; close competing workloads |
| Another process owns the run | Wait for or stop that process; do not delete its lock file to bypass ownership |
| Proxy, network, or exchange timeout | Check the actual network and exchange availability; inspect observation health before paper use |
| Failed/interrupted training | Read `status.json`, fix the cause, and rerun the same command |

No software can guarantee zero crashes from hardware instability, power loss, full disks, operating-system termination, or external outages. This release tests specific failure paths and reports failures clearly; it does not certify unattended operation or profitable trading.
