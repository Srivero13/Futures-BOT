# Futures-BOT 2.0 — NautilusTrader v2 integration, milestone 1

Status: **experimental read-only branch**, no trading strategy integration, no
real or paper orders, and **no performance/alpha assertion**.

This work begins from the existing `develop` branch, not `main`. The
branches have diverged, so do not force-merge them. The existing spot paper
coordinator, SQLite financial state, risk gates, WBC01-F01 registration and
research protocols remain unchanged. There is **no authorization to deploy
trading**, promote research models or run any live Nautilus nodes.

## Why Nautilus

NautilusTrader provides a Rust event-driven backtesting/execution engine with
Python strategy APIs. Version 2 is a pre-release and differs from stable v1.
Selected experiment pin: `nautilus_trader==2.0.0rc7` (released 2026-10-15).
Upstream v2 currently supports Python 3.13/3.14; the existing bot targets
Python 3.12. Keep them in separate virtual environments.

Upstream references:
- https://nautilustrader.io/docs/latest/getting_started/installation/
- https://github.com/nautechsystems/nautilus_trader/blob/develop/docs/getting_started/quickstart.py
- https://github.com/nautechsystems/nautilus_trader/blob/develop/docs/getting_started/backtest_low_level.py

NautilusTrader uses LGPL-3.0-or-later. Review distribution and linking
obligations before packaging or shipping combined software.

## Phase-1 scope

`integrations/nautilus_bridge.py` is a narrow, opt-in adapter for the
existing downloader's Binance BTCUSDT/ETHUSDT **one-minute spot** shards.
Each CSV must carry the normal `*.json` sidecar with the same symbol,
venue, timeframe, length, first/last timestamps, bytes and SHA-256. Missing
minutes fail closed by default; `--allow-gaps` preserves/records gaps without
fabrication and must not be treated as continuous-market evidence.

All decimals must fit 8 places. Instrument precision is a fixed experiment
assumption, **not verified exchange tick-size, lot-size or fee metadata**.
Quotes, order books and subminute microstructure are **not** represented by
one-minute candles; do not infer fills, execution latency or an edge from
this replay.

A candle opens at its source `timestamp` (UTC seconds) and becomes causally
available only on **close**, exactly 60 seconds later. The Nautilus `Bar`
has `ts_event == ts_init == (timestamp + 60) * 1e9`, avoiding any appearance
that its finalized high/low/close were known at the opening minute. Original
source open seconds and SHA-256s remain in the audit report.

Both commands only read the provided data. `audit` runs without Nautilus:

```bash
python -m unittest discover -s tests -p 'test_nautilus_bridge.py' -v
python -m integrations.nautilus_bridge --files data/market/binance-BTCUSDT-2025-04.csv
```

For **Nautilus 2.x native backtest replay**, create a separate environment
on Linux with Python 3.13; do not replace or install into `~/projects/Futures-BOT/.venv`:

```bash
python3.13 -m venv .venv-nautilus
.venv-nautilus/bin/python -m pip install -r requirements.txt
.venv-nautilus/bin/python -m pip install 'nautilus_trader==2.0.0rc7'
.venv-nautilus/bin/python -m unittest discover -s tests_nautilus -v
.venv-nautilus/bin/python -m integrations.nautilus_bridge --mode replay \
  --files data/market/binance-BTCUSDT-2025-04.csv
```

Max input is 50,000 candles in this first-stage in-memory bridge (~one month),
unless `--max-bars` is deliberately raised. Neither mode writes a state
database or changes approved-model flags. The only strategy registered in
`replay` counts events. The simulation venue is `RESEARCH` and its
account balance is entirely synthetic. No exchange client is initialized.

These are engineering tests, not proof of parity between the current model and
Nautilus execution. The audit and replay JSON now include `source_parse_seconds`,
`native_event_build_seconds`, `native_run_seconds` and dispatched bars/second.
These are wall-clock measurements on the executing host and include a slow,
Python-based feature-parity observer: they are **not** end-to-end order latency
or an apples-to-apples legacy-engine comparison. No real-data benchmark has
been claimed yet. Compare identical input hashes and include
parser time, native event processing time, peak RSS and per-run count/ordering
before claiming performance improvement.

## Architecture boundary and staged roadmap

| Existing system | Initial decision |
| --- | --- |
| `download_v15_data.py`, `engine_v1/dataset.py` | Keep; verify provenance and reuse CSV |
| `engine_v1/training.py`, `engine_v1/model.py`, research scripts | Keep independent; no model promotion |
| `engine_v1/core.py` / SQLite ledgers | Keep as accounting reference; no shared write access |
| `engine_v1/stream.py` | Keep unchanged; do not cross-wire two active coordinators |
| `run_system_acceptance.py` | Keep; the observed timeout/reconnect still needs repeat verification |
| Frozen WBC01-F01 | Keep separate until its already registered window closes |

1. **Milestone 1**: offline audit, native counting replay, source integrity,
   close timestamps, no-orders guarantee and isolated tests. The native replay
   also verifies SHA-256 fingerprints of all six original causal features on
   each fully warmed 21-candle window. Gaps reset the feature window.
   This verifies event-to-feature parity, not model economic validity.
2. **Milestone 2**: deterministic parity harness with identical strategies and
   causal decision times, independent simulated fee/impact reconciliation,
   gap/reset handling, runtime and memory benchmarking.
3. **Milestone 3**: order-book/quote event conversion with source timestamps,
   sequence integrity and delayed execution modeling; preserve historical
   dataset boundaries and avoid contaminated evaluation periods.
4. **Milestone 4**: shadow (no orders) real-time observation with host/network
   health, checked loss/restart recovery and well-defined kill switches.
5. **Milestone 5**: separate testnet/paper execution study, venue metadata,
   partial fills and cross-engine reconciliation. Real orders require a
   separate risk and profitability review; they are out of scope now.

## Remaining risks and limits

- The plugin uses a v2 release candidate: native compatibility must be confirmed
  by GitHub Actions on Python 3.13 and by a host-specific smoke test.
- The CSV hash/sidecar proves local byte consistency, not source authenticity.
- Observing 1-minute bars is **not** validating subsecond scalping.
- Native `on_bar` callbacks and the legacy training-label semantics must be
  compared explicitly before trading strategies can be ported.
- Existing research had no approved after-cost profitable strategy; engineering
  acceptance does not change that conclusion.
