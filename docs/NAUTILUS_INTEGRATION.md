# NautilusTrader integration — first working milestone

The isolated integration uses NautilusTrader 1.231.0, tested with Python 3.12 on
Linux x86-64. Its Linux wheel requires glibc 2.35 or newer (Ubuntu 22.04+).
Use a separate environment: existing CPU/GPU research dependencies are unchanged.
The pinned dependency set is in requirements-nautilus-lock.txt. Other platforms
need separate compatibility verification. NautilusTrader is LGPL-3.0 licensed;
retain upstream notices and review its terms before distributing modified builds.

## Run the offline accounting control

From the repository root:

```bash
python3.12 -m venv .venv-nautilus
.venv-nautilus/bin/python -m pip install -r requirements-nautilus-lock.txt
.venv-nautilus/bin/python -m unittest discover -s tests_nautilus -v
.venv-nautilus/bin/python -m integrations.nautilus.control \
  --output "data/nautilus-control-$(date -u +%Y%m%dT%H%M%SZ).json"
```

No API keys, network requests, real orders or market downloads are used by this
control. Installation requires package downloads. The replay should finish in
seconds; it is not an overnight training task.

Two separate BacktestEngine instances represent isolated spot cash accounts.
Each buys one synthetic ETH at ask 100.10 and sells at bid 101.00 or 99.00,
with explicit hypothetical 10 bps fees, zero added slippage and zero latency.
Actual Nautilus fills and commission currency are checked, not only totals.
The same quotes and decisions are replayed through engine_v1.core.Portfolio.
Both engines must be flat and their fees/cash must equal independent Decimal
arithmetic. Expected final cash: 1000.6989 and 998.7009 USDT respectively.
A failed check raises an error; no success report is written. Existing reports
are refused. Unexpected Nautilus versions fail before simulation.

This is simulation compatibility, not live multi-account routing or evidence of
profitability. The SIM instrument is deliberately synthetic; its precision and
fees are not claimed to represent current Binance contract specifications.
There is no futures margin, liquidation, funding, queue position or latency model.
Pandas may emit an upstream Timestamp.utcnow deprecation warning; it does not
change the accounting result.

## Migration boundaries

Keep frozen WBC01 files, registrations, source data and previous failed research.
Reuse provenance validation, causal features, research protocols and cost/risk
checks. New integration modules live under integrations/nautilus; the existing
paper engine remains an independent accounting reference during migration.
Do not copy its order lifecycle into Nautilus or treat a model's approval field
as approval for a new execution path.

Following this control, import audited historical candles with explicit close
availability timestamps and venue identity. Check count, precision, gaps and
source hashes against the existing ingestion. Candle replay cannot establish
order-book fills. Then validate public-feed observation and simulated execution,
reconnect/stale-data behavior, isolated account state and global exposure caps.
Live clients and credentials are outside this milestone.

The official website may show 2.x examples. This integration was exercised
against the installed 1.231.0 API; do not mix those APIs or upgrade silently.

## Historical candle replay

```bash
.venv-nautilus/bin/python -m integrations.nautilus.historical \
  --csv data/market-expanded/binance-ETHUSDT-2026-08.csv \
  --symbol ETHUSDT --date 2026-08-01 \
  --output "data/nautilus-historical-$(date -u +%Y%m%dT%H%M%SZ).json"
```

The adjacent .json provenance sidecar must identify Binance spot, the requested
symbol, one-minute candles, matching CSV SHA-256, row count and first/last open.
The whole shard is parsed and its bounds verified. The selected UTC day must
contain exactly 1440 contiguous minutes. Input hashes are checked again after
replay. Raw exchange archives are not re-downloaded or independently audited.
BTCUSDT is also supported. Requested days and entire source shards must precede
the frozen September 1, 2026 development boundary.

Canonical CSV open timestamps (seconds) become Nautilus bar event/init timestamps
at candle close (nanoseconds). Each strategy callback is checked against that
close time and every OHLCV value contributes to the replay digest. Prices must
fit two decimals and volume eight decimals exactly; rounding is rejected.
The instrument is for data conversion only, not historical exchange filters.
Bar execution is disabled and the observer has no order-generation code.

The success status is historical_replay_passed. This verifies data delivery,
not a backtest of a strategy. Local tests use generated data; run the command
above to check the operator's actual dataset.

## Initial integration milestones

1. Offline accounting parity: passed locally and reported passed by operator.
2. Historical data replay: passed locally and on operator ETHUSDT data for August 1, 2026.
3. Public-feed observation: implement and validate freshness/reconnect handling.
4. Two-account simulated operation: validate isolation, global risk, stale-data
   entry blocking and recovery under an integrated acceptance run.

Two of four operator-validated milestones are complete (50% by milestone count).
These milestones are not equal effort and do not measure whole-project completion,
strategy profitability, live-execution readiness or remaining calendar time.
A validated strategy, actual execution constraints and live operational controls
remain separate requirements. Existing frozen forward research is unchanged.


## Public quote observation (milestone 3)

```bash
.venv-nautilus/bin/python -m integrations.nautilus.observe \
  --seconds 300 \
  --output-dir "data/nautilus-observe-$(date -u +%Y%m%dT%H%M%SZ)"
```

This uses the installed Nautilus Binance SPOT data adapter for BTCUSDT and ETHUSDT.
No execution factory is registered, exec_clients is empty, and key/secret are None.
An Actor subscribes to quotes; there is no trading Strategy or order submission.
No credentials are required. A warning about absent execution clients is expected.

The process runs for 300 seconds including startup, then stops. Progress prints
approximately every ten seconds. Artifacts: run.json (supervisor outcome),
health.json (latest observation), observation.json (completed worker checks), and
adapter.log (upstream warnings/errors). If startup or shutdown fails, observation.json
may be absent; run.json and adapter.log remain the diagnostics. Existing run
directories are refused. A parent process terminates a stuck worker after the
requested duration plus 60 seconds, escalating to SIGKILL after five seconds.
The log budget is 64 MiB, checked every ten seconds (so slight overshoot is possible).

Freshness uses local monotonic receipt time, sampled once per second, with a fixed
one-second maximum age after a 60-second startup allowance. Missing either symbol
is stale. All stale samples are retained even when freshness recovers. A local
wall/monotonic drift greater than 250 ms is latched as a clock failure. Bad/crossed
quotes are counted and rejected. Final checks require both symbols, no stale
samples after warmup, valid quotes, stable clock, no orders and clean shutdown.
This intentionally does not relax the criterion after a disconnection.

Observed freshness recovery is not a socket reconnect count. The adapter handles
its own transport; inspect adapter.log for its errors. Passing observation checks
does not certify error-free transport or continuous subsecond coverage. Recovery
needs an explicit interruption exercise before milestone 3 is complete.

Local validation builds the real data-only node without connecting and tests
staleness/recovery, clock jumps, invalid quotes and supervision failures. The
live Binance run must be verified on the operator's network. This is not a
five-hour training job and does not modify frozen research or market datasets.
