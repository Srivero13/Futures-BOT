# ETH relative-recovery experiment RR-01

Status: closed after failure of all four development screens; unapproved.
See [RR-01 closeout](RR01_CLOSEOUT.md). The command below is retained for reproduction. This document
defines the rule before this runner's market-data results are inspected.
March–August 2026 was already used in other studies; this is not an untouched
holdout or an independently preregistered validation.

## Economic hypothesis and difference from earlier attempts

A temporary ETH-specific decline during a stable/rising BTC market may partly
reverse after ETH starts recovering. BTC provides market context; a rolling
relationship estimates whether ETH's decline is unusual relative to that
context. This is a hypothesis, not an established causal mechanism.

Earlier ETH reversal rules ignored this conditional market relationship.
Earlier BTC-context regressions forecast all hourly ETH returns using a small
linear feature set. RR-01 instead tests a fixed interaction: a large negative
residual, non-falling BTC, and an already observed ETH recovery. It does not
invert a failed model or lower fees. Those earlier failures remain relevant
evidence; adding these conditions may simply yield another failed or sparse rule.

## Fixed rule and causal availability

At each UTC hour t, use closes available by t (the last bar opened at t−1 minute).
Require 1501 consecutive aligned ETH/BTC minute closes: 25 hours plus endpoints.

1. Compute 25 non-overlapping hourly log returns for each asset.
2. Regress the first 24 ETH returns on the first 24 BTC returns, with an
   intercept. The latest hour is excluded from fitting.
3. Calculate the latest ETH residual against that fitted relationship and its
   z-score using the prior residual standard deviation, with 22 residual degrees
   of freedom and a floor of 0.000001 log-return units.
4. Enter only when all conditions hold: positive fitted beta; latest BTC hourly
   return at least zero; residual z-score below −2; residual below minus twice
   the round-trip cost hurdle (approximately −52 log-bps); ETH's last five-minute
   return strictly positive.

BTC centered return sum of squares must exceed 1e−12. Insufficient variation
means no signal. There is no coefficient clipping or parameter search.
The thresholds are discretionary fixed design choices, not fitted optimal values.
An observed deviation larger than costs is not a forecast of future recovery.

## Execution, risk, and benchmarks

Trade ETHUSDT spot long-only. BTC is not traded and this is not a hedged strategy.
Make decisions hourly; enter at the minute open one minute after the decision;
exit 60 minutes after entry. One position at a time; a signal arriving before
the current position exits is ignored. No entry may leave a position beyond
the monthly evaluation boundary.

Each month independently starts with 1000 quote units and targets 100 quote
units per entry, with quantity rounding and minimum notional inherited from the
existing simulator. Fees are 10 bps per side, slippage 2 bps per side, full spread
2 bps. No leverage, short selling, stop-loss, or automatic deployment is added.

The cash benchmark has zero P&L. Reports include all simulated trades, causal
signal details, fees, marked drawdown, concentration, and extra-slippage stress.
Stress uses fixed quantities and times; it is not a new strategy run.
Monthly profit sums are not compounded portfolio returns. No buy-and-hold
outperformance claim is made.

## Budget and decision

Budget: one rule, one parameter configuration, six March–August monthly
development evaluations. September onward stays reserved. No GPU training,
threshold sweep, or automatic search follows a failure.

Use the same existing development screens: at least 30 closed trades, at least
four profitable months, positive total after removing the best trade, and
positive total with an additional 1 bps slippage per side. Failure of any screen
means insufficient development evidence; do not tune the thresholds on those
results. Passing all screens still provides no approval: freeze the candidate
and define fresh independent validation and uncertainty analysis separately.

## Limitations and run

The 24-point rolling regression can be unstable. Candle reference prices,
fixed full fills and static costs do not reproduce actual fills or intrabar
risk. Serial dependence, repeated research on this period, and discretionary
hypothesis selection limit inference. No significance or profitability claim
is supplied by the engineering screens.

```bash
python research_relative_recovery.py \
  --eth data/market-expanded/binance-ETHUSDT-*.csv \
  --btc data/market-expanded/binance-BTCUSDT-*.csv \
  --output data/eth-relative-recovery-development.json
```

Input provenance is verified, the protocol is written before signals or outcomes
are evaluated, and inputs are fingerprinted again after the run. Existing output
or protocol paths are refused. Missing joint coverage or warmup fails instead of
silently dropping examples.

```bash
python -m unittest discover -s tests -p 'test_relative_recovery.py' -v
```
