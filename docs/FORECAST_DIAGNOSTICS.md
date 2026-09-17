# Explain zero-trade model results

`diagnose_v16.py` measures how the existing model's raw forecasts and calibrated
lower bounds compare with the execution backtest's cost threshold. It does not
train, change a model, simulate fills, send orders, or grant approval.

Use Python 3.12 with the project's pinned requirements. Supply a completed v1.6
model, chronological Binance one-minute CSV shards, and their checksum sidecars.
Use at least 21 preceding candles for feature warm-up. No API keys are needed.

```bash
python diagnose_v16.py \
  --files data/market-expanded/binance-ETHUSDT-*.csv \
  --model MODEL_DIRECTORY/model.json \
  --start 2026-07-01 \
  --end 2026-09-01 \
  --output data/eth-forecast-diagnostic.json
```

Replace MODEL_DIRECTORY with a completed training directory. Dates are UTC,
end-exclusive, and must begin at or after calibration. Existing reports cannot
be overwritten. Progress appears per evaluation batch after checksum verification.
The model and source checksums are rechecked before publishing the report.

## Interpretation

- `raw_forecast_above_threshold`: forecasts exceeding the threshold before
  subtracting the calibration buffer. These are diagnostic counterfactual counts,
  not a recommendation to remove the buffer.
- `blocked_by_calibration_buffer`: those raw candidates that fail after subtracting
  the buffer. This does not establish that the buffer is incorrectly calibrated.
- `calibrated_forecast_above_threshold`: lower bounds passing the unchanged gate.
- `threshold_shortfall_log_bps`: threshold minus lower bound; positive values
  fall short, negative values pass. Exact equality does not pass.
- `prediction_log_bps`, `buffer_log_bps`, `lower_bound_log_bps`, and
  `actual_return_log_bps`: distributions on the same model-accepted examples.
- `lower_bound_coverage`: fraction of observed labels above the lower bound;
  descriptive coverage, not confidence in profits or statistical significance.

The default threshold is approximately 28.000007 log-bps: exact round-trip
break-even for 10 bps fees per side, 2 bps full spread, 2 bps slippage per side,
plus a 2 log-bps margin. These are declared assumptions, not fetched account
fees. Optional `--fee-bps`, `--spread-bps`, `--slippage-bps`, and `--margin-bps`
record an explicit scenario; do not tune these merely to produce trades.

Means, extrema and counts use every accepted example. Quantiles are exact up to
100,000 accepted examples, then use a deterministic uniform reservoir and are
marked approximate. Memory is bounded by batch size and five reservoirs.
Linear, polynomial, and supported volatility-scaled linear models are handled;
scaled models use their per-example scale for the calibration buffer.

Labels overlap and use next-open to horizon-later-open returns. No execution
delay or position availability is modeled. Label-end filtering excludes the
last few examples, so counts may differ from the execution backtest. Gaps reset
feature windows, but this diagnostic does not certify uninterrupted coverage.
All-OOD intervals report null distribution/error metrics; empty intervals fail.

The report records source, model, and relevant implementation hashes. Results
from previously examined periods remain retrospective. A weak forecast requires
a new, predeclared research hypothesis and separate validation; repeated fitting
of identical data will not improve it. Keep existing artifacts for comparison.
