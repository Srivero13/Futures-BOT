# Current research checkpoint — 2026-10-15 UTC

No strategy is approved and no profitable deployment has been established.
Software validation and economic evidence are separate requirements.

## What has been verified

- GitHub Actions runs the base regression suite and a separate suite with Numba
  and PyTorch CPU dependencies. The optional job fails on any skipped test.
- The operator's GTX 1660 passed the fixed CUDA synthetic learning control with
  PyTorch 2.7.1+cu118. Evaluation MSE was 0.2747515059 versus 12.7177685053 for
  the zero predictor. This verifies that control, not market forecasting skill.
- The operator reported 401 tests run, zero failures and one optional Numba skip
  before the subsequent accounting/basis additions. Counts are revision-specific;
  this is not a claim that every test executes on CUDA.
- Sequence accounting reconciles reference P&L, costs and supplied funding, and
  now carries conservative mark-OHLC bounds across trades. It does not model
  capital, margin, liquidation, contract rounding or actual fills.

## Research decisions

| Study | Evidence supplied by operator | Disposition |
|---|---|---|
| UM01 | 194 trades over two separate August runs; summed net -26.111688 USDT | Closed, rejected development; not a continuous portfolio |
| UM02 | 93 trades; net -7.568643 USDT; best-trade removal and extra-impact tests negative | Rejected development |
| BASIS-Q01 | Three live pilots; 12 anchors per horizon; all eight cost-scenario means negative (-29.17898 to -31.01087 bps), zero positive subtotals; hypothetical fees | Cost-scenario evaluation complete; no candidate advanced |
| BASIS-D01 | 10,080 aligned candle minutes; 167 common anchors; small basis changes, no executable quotes | Diagnostic complete; no strategy advanced |

See [UM01 closure](USDM_UM01_CLOSURE.md), [UM02 protocol](USDM_UM02_PROTOCOL.md)
and [basis study](USDM_BASIS_STUDY.md). CPU/GPU upgrades and passing tests do not
reverse these research outcomes. Raw datasets and local result reports are not
committed to the repository.

## Requirements before another strategy experiment

1. Specify a new economic hypothesis and its available-at-decision inputs before
   evaluating returns. A winning subset of a rejected run is not new validation.
2. Identify a data source that can test that hypothesis. For a two-market basis
   hypothesis, matched candle timestamps cannot establish simultaneous bid/ask
   prices, order latency, available size or two-leg fills.
3. State both-leg costs, funding treatment, financing assumptions and exposure
   constraints. Explicit hypothetical scenarios remain hypothetical; saved spot
   fees do not verify futures fees or historical account conditions.
4. Freeze chronological development and evaluation ranges, exclusions, finite
   experiment budget and decision criteria before revealing evaluation outcomes.
   Check actual prior data use before calling any range untouched. The designated
   September reserve is not automatically opened by the recent diagnostics.
5. Preserve failures and stop at the declared budget. A positive development
   result requires independent evaluation; it never automatically enables orders.

There is no active overnight training job required by this checkpoint. Repeating
completed controls or searching more variants on August cannot supply missing
execution evidence. The remaining work is research design and suitable data,
followed by execution/risk validation if a candidate earns that progression.

The [live basis pilot review](BASIS_QUOTE_PILOT_REVIEW.md) preserves all eight
predefined direction/horizon results. Its evidence is operator-reported and
descriptive; further short-capture repetition is not an active task.

## WBC01 development screen and risk replay

[WBC01](WEEKLY_BTC_CONTROL.md) defines one weekly BTC spot momentum control using
previously used development data. It is motivated by primary historical research
and addresses a different holding horizon, with explicit costs and baselines.
The operator reports 37 trades and a passed original development screen: base net
48.2748 USDT versus 78.5453 for buy-and-hold. Profit is concentrated in 2024 and
the partial 2026 result is negative. Minute reference risk replay is now available;
independent validation and promotion have not occurred.
It does not replace the original scalping goal with a claim of weekly success.

The operator's minute risk replay reconciled all scenarios (base sampled
3.70737%, OHLC upper bound 3.72598%). A separate
[WBC01-F01 prospective protocol](WEEKLY_BTC_FORWARD.md) and local registration
command are available for October 26, 2026–April 26, 2027 UTC. Registration and
future evaluation are pending; no scheduler, orders or promotion are started.

The operator registered WBC01-F01 at 2026-10-21T03:56:33.635458+00:00, before its
fixed evaluation start. The consolidated evaluator is implemented: one command
validates the binding, builds signals, applies costs, replays risk and reports
results after the registered interval. A readiness-only mode is available now.
This reduces manual work; it does not shorten the calendar or validate scalping.
