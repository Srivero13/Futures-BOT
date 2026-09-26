# Development phase closeout

Decision recorded after the operator's 2026-09-25 results: **close the current
development-testing phase with no candidate promoted**. All evaluated models
and strategies remain research-only. This is a research disposition, not a new
runtime guard, software certification or claim that profitable trading is impossible.

## Final experiment

The every-minute breakout retained the 24-hour lookback, four-hour hold,
one-minute entry delay, single-position limit, costs and failure screens of
the original hourly variant. It increased completed trades from five to 162
but did not establish a profitable configuration.

| Metric | Every-minute result |
|---|---:|
| Completed trades | 162 |
| Positive months | 2 of 6 |
| Sum of independent-month net P&L | -20.832687600450167 USDT |
| Net P&L excluding best trade | -28.492326570129487 USDT |
| Net P&L with extra 1 bps slippage per side, fixed quantities | -24.073812401103556 USDT |
| Development screens failed | 3 of 4 |

The sample-count screen passed; positive-month, best-trade-removal and slippage
screens failed. The sum is not a compounded six-month return because capital
reset monthly. Fixed-quantity slippage attribution is not a fresh portfolio
simulation. No real orders were placed by these research scripts.

## Disposition of completed approaches

| Approach | Disposition and reason |
|---|---|
| Candle linear/polynomial and GPU variants | Retain as benchmarks; no demonstrated economically useful forecast advantage |
| Frozen microstructure models | Predictive signal observed in supplied captures, but selected average returns far below costs |
| Hourly normalized trend | Small base surplus, erased by modest extra slippage; concentrated in a winning trade |
| BTC-context hourly forecasts | Minimal pooled improvement, inconsistent by month; no qualified forecasts under the fixed cost gate |
| Hourly 24-hour breakout | Five trades; inadequate sample and concentration. Hourly sampling excluded most qualifying minutes |
| Every-minute 24-hour breakout | Sampling limitation addressed; 162 trades still lose under the stated costs |

The sampling audit's 717 qualifying minutes are not 717 independent opportunities
or fills. Related observations can occur during an already open position.
The minute variant does not retroactively replace the hourly report.

## Evidence and preservation

Results here are transcribed from operator-supplied console summaries. The
repository workspace did not independently execute the full market-data runs.
Keep the original local JSON reports, their protocols, source CSVs and checksum
sidecars. Do not commit account screenshots, credentials or raw private reports.
The machine-readable [decision record](../reports/development/phase-closeout.json)
identifies the relevant local artifact names and evidence origin.

Earlier consolidated evidence is in [the research review](RESEARCH_REVIEW.md).
It covers studies available when that dossier was created; the final breakout
results are recorded here rather than overwriting that earlier artifact.

March–August 2026 has been inspected repeatedly. It is development data,
regardless of historical CLI labels such as "test". September remains reserved
for these historical strategy experiments. This reservation is not proof that
every September market observation is unseen: separate live microstructure
recordings from September have already been inspected.

## Boundary for the next phase

Do not start another parameter sweep, invert a failed signal, change fees to
rescue a result, or unseal the reserved data merely to continue activity.
The current phase has no pending training or diagnostic requirement.

Further strategy research must start with a written, distinct economic
mechanism and an explicit experiment budget. Specify the instrument, data
availability, causal features, executable target, benchmarks, costs, risk
constraints and failure criteria before running it. List every attempt and
explain how it differs from already unsuccessful hypotheses.

A development candidate would still need a frozen protocol evaluated on data
that was not used to choose it, uncertainty analysis appropriate for dependent
observations, and prospective execution/paper validation. A fixed calendar
period or engineering screen alone cannot supply that evidence. Reserve access
must be explicit and logged; no command in this closeout accesses it.

Do not equate completed software tasks with a probability of profitability or
promise a completion date. The tested pipeline is useful research infrastructure;
finding a defensible economic advantage remains an unresolved research problem.
