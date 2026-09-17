# Fixed normalized-decline execution experiment

This experiment asks whether extreme declines relative to recent volatility
precede rebounds strong enough to cover the existing execution assumptions.
It is a new development hypothesis motivated by weak mean-reversion ranking,
not an approved model or a demonstrated improvement.

## Predeclared rule

- Symbol: supplied Binance spot symbol, initially ETHUSDT.
- Features: existing closed-candle 20-minute log return and standard deviation
  of the preceding 20 one-minute log returns.
- Score: `-momentum_20 / (max(volatility_20, 0.000001) * sqrt(20))`.
- Threshold: maximum of zero and the preceding calendar month's 99th percentile
  score on the UTC 15-minute decision grid. This percentile is fixed, not optimized.
- Entry: score strictly exceeds threshold, one pending entry/position at a time.
- Decision cadence: once every 15 minutes on the UTC grid.
- Entry fill: following minute's open, plus declared spread and slippage.
- Exit: open 15 minutes after actual entry, less spread/slippage and fees.
- No entries whose scheduled exit lies outside the test month. No stop loss.

Calibration requires every grid observation, including preceding 21-bar warm-up,
and at least 100 finite scores. It uses no future returns. Quantiles are exact
with a 100,000-score cap. Gaps or insufficient warm-up stop calibration; test gaps
stop execution. The fixed volatility floor prevents division by zero; it does not
make a score statistically normal or equivalent to a calibrated probability.

This is a rule, not a return forecast. It intentionally uses no model OOD filter,
forecast lower bound, or forecast-cost entry gate. The existing model entry path
remains unchanged. Costs are charged to each simulated trade; the purpose of the
experiment is to measure whether the rule survives them. The reference cost-plus-
margin field is informational, not an applied rule threshold.

## Run on development data

```bash
python reversal_v16.py \
  --files data/market-expanded/binance-ETHUSDT-*.csv \
  --symbol ETHUSDT \
  --first-test 2026-03-01 \
  --months 6 \
  --reserve-from 2026-09-01 \
  --output data/eth-normalized-reversal-development.json
```

Use the existing Python 3.12 environment and base requirements. No GPU, keys or
network access are needed. Verified CSV sidecars must identify the symbol,
Binance venue, one-minute timeframe, checksum and last candle before the reserved
date. Earlier history is allowed for warm-up. September remains excluded.

Costs are fixed to the existing simulator defaults: starting cash 1,000 quote
units per month, maximum 100-unit order notional, 10 bps fee per side, 2 bps full
spread, and 2 bps slippage per side. Quantity step is 0.000001 and minimum notional
is 5. These are assumptions, not fetched historical account fees or filters.
Do not interpret them as universally valid for every symbol.

A `.protocol.json` records the rule, dates, cost assumptions, sources and code
hashes before evaluation. Changed protocols require a new output path; existing
aggregate reports are protected. An output lock prevents concurrent runs to the
same report path. Progress shows calibration, bars, trade counts and monthly P&L.
After interruption, rerun; this experiment recomputes folds, not partial positions.
The protocol persists but the complete aggregate is published only after success
and an input checksum recheck. Source data and model artifacts are never changed.

## Interpretation and limits

The final summary includes trade counts, monthly net P&L, fees, spread/slippage
cost already embedded in fills, and open/close sampled liquidation-value drawdown.
Every month starts with fresh 1,000-unit cash. The sum of monthly net P&L is a sum
of independent-month experiments, not compounded portfolio performance. Costs
embedded in fill prices must not be subtracted twice.

Full trade and hourly marked-equity records are in the JSON report. Minute bars
cannot reproduce millisecond fills, partial fills, queue position, market impact,
historical exchange filters or intrabar drawdown. Funding, interest and machine
operating costs are excluded. No real broker orders, risk-policy changes or model
approval occur. Previously flagged price/volume events remain in the sample.

March–August is development data already examined under other hypotheses. Positive
results would justify further scrutiny, not proof of statistical significance or
permission to trade. Do not repeatedly tune the percentile against these results.
The reserved-date guard is local to this runner and cannot prove the period was
unseen through other tools. No reserved data is automatically evaluated.
