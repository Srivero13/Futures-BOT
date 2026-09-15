# System requirements and compatibility

Futures-BOT 1.5 is a CPU-based research and paper-trading application. It uses public market data and virtual balances. No exchange account, API key, GPU, paid data subscription, or funded account is required for the included workflows.

## Hardware planning

These are conservative setup budgets, not experimentally certified minimum specifications. The test suite and benchmarks ran in a Linux x86_64 development environment; low-end hardware and 30+ GB datasets have not been certified.

| Component | Suggested minimum: observation and small research runs | Recommended: larger historical research |
|---|---|---|
| CPU | 64-bit x86 processor, 2 cores | Modern 4+ core x86 processor |
| RAM | 4 GB system RAM | 8–16 GB system RAM |
| Free project storage | 5 GB, excluding the operating system | SSD with 100 GB free for a 30 GB corpus, staging, logs, and backups |
| GPU | None for computation; display hardware only if using a desktop OS | No dedicated compute GPU required |
| Network | Stable HTTPS and secure WebSocket access to selected public exchanges | Wired connection; measure latency on the actual runtime host |
| Clock and power | Synchronized system clock; host awake during sessions | Disable suspend while running supervised sessions |

Storage grows with the chosen instruments, dates, raw-data format, and audit history. The recommended 100 GB is a planning allowance, not a downloader requirement or a throughput guarantee. Increase it for larger collections. Training memory is controlled by `--chunk-size`; the default is 8,192 examples plus a small causal overlap. Multiple simultaneous training jobs each need their own memory budget.

## Software

| Component | Setup target / validation status |
|---|---|
| Operating system | Ubuntu 24.04 LTS, Desktop or Server, for the documented installation path |
| Python | Python 3.12; release tests ran on 3.12.14 |
| Base numerical library | NumPy `>=1.26,<3`; tests used 2.3.5 |
| WebSocket client | websocket-client 1.8.0 |
| Optional compiled inference | Numba 0.63.1 and NumPy `>=1.26,<2.4`, installed through `requirements-fast.txt` |
| Tools | Git, pip, Python venv, trusted CA certificates |
| Optional service management | systemd user services on Linux |

A desktop environment is optional. The bot and training commands run in a terminal and can operate on a headless host. Full Ubuntu installation, reboot behavior, and hardware-specific drivers were not validated in the development container. Windows and macOS are not validated release platforms; the Linux bootstrap and systemd instructions do not apply to them. ARM and other Python/library versions are not part of the tested matrix.

## Data compatibility

The running observer/paper engine supports Binance spot BTCUSDT and ETHUSDT by default. The v1.5 research downloader supports Binance one-minute spot archives and Coinbase one-minute candles. Coinbase acquisition support is separate from live trading support. Fresh downloads timed out during release validation; fixture tests cover adapter behavior.

Local training imports accept chronological CSV or CSV.gz files with `timestamp,open,high,low,close,volume`. Timestamps must be UTC seconds aligned to one minute. Price/volume strings must be finite with valid OHLC bounds. Files in a training invocation must belong to one venue and symbol and must not overlap. Data gaps are allowed but reset feature and target windows. No futures, stocks, forex, or pooled multi-venue training is implemented in this release.

## Next steps

Follow the [README quick start](../README.md), then the [operations guide](OPERATIONS.md) for observation, local timing, backups, and optional services. Use the [v1.5 data and training guide](V1.5.md) for acquisition, model evaluation, and batch benchmarks. Research models are unapproved by default; passing installation checks does not establish a trading edge.
