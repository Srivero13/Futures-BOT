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
| BASIS-Q01 | Three consecutive live pilots; 12 common anchors per horizon; largest pooled quote-reference mean +0.81069 bps before fees | Diagnostic complete; no candidate advanced |
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
