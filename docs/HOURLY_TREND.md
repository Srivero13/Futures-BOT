# Hourly trend development experiment

This is one fixed, unproven hypothesis: strong 20-minute upward movement may
continue over a 60-minute holding period. It is separate from the frozen
five-second models and earlier 15-minute reversal experiment. It sends no orders.

At each UTC hour, using only the preceding 21 completed minute candles:

1. Compute momentum_20 / (max(volatility_20, 0.000001) * sqrt(20)).
2. Require it to exceed max(0, preceding-month 95th percentile), calibrated
   only on hourly observations with complete warm-up history.
3. Require past 20-minute log return to exceed twice estimated round-trip cost
   (approximately 52 log-basis-points). This is a past-movement filter, not a
   forecast cost gate or an assertion of positive expected returns.
4. Enter one minute later and exit 60 minutes after entry. Hold at most one
   position. Reject entries that cannot close before the monthly boundary.

Costs remain 10 bps fees per side, 2 bps slippage per side and 2 bps full spread.
Unlike the quote-target studies, candle reference prices do not already include
an ask-to-bid spread. This convention implies about 26 bps round-trip cost.
The simulator's separate 2 bps forecast margin is reported but is not an entry
condition for this rule. Position notional is 100 from initial capital 1000.

```bash
python -u research_hourly_trend.py \
  --files data/market-expanded/binance-ETHUSDT-*.csv \
  --symbol ETHUSDT \
  --first-test 2026-03-01 --months 6 \
  --reserve-from 2026-09-01 \
  --output data/eth-hourly-trend-development.json
```

Inputs must have matching checksum sidecars and cannot enter the reserved dates.
A protocol containing sources, code hashes, costs and fixed settings is written
before evaluation. Existing output is rejected; no model or capture is modified.
Monthly progress and results are printed. Each month resets capital, so summed
P&L is not a compounded portfolio return. Gap-crossing fills are rejected.

These months have already been inspected in earlier research. This is development,
not independent confirmation or a preregistered untouched holdout. Neither more
holding time nor fewer trades guarantees profitability. Do not tune thresholds
until these months look profitable. A positive development result would require
a frozen protocol tested on new data and more realistic execution validation.

The simulator assumes full fills, fixed costs and hypothetical quantity filters;
it does not model queue position, historical exchange filters or intrabar risk.
The reported maximum drawdown samples opens and closes only. No stop-loss,
funding, taxes or infrastructure expenses are included. All outputs stay unapproved.

## Saved-trade robustness

```bash
python diagnose_hourly_robustness.py \
  --report data/eth-hourly-trend-development.json \
  --output data/eth-hourly-trend-robustness.json
```

This checks saved trade accounting and reports concentration after removing the
best trade, plus fixed extra slippage of 0, 0.5, 1 and 2 bps per side. Reference
prices are recovered from the original impact assumptions, adverse impact is
increased, and fees are recomputed on the new fills. Quantities and trade times
remain fixed. This is attribution, not a replay: a full simulation could change
position sizing, cash constraints and entries. Zero stress must reconcile with
the original totals. It neither reads the reserved period nor changes the rule.
