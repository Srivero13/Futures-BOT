# UM01: fixed causal momentum development experiment

This is a first integration of signal selection with sequential futures accounting.
It is not a trained model or approved strategy. August 1–7, 2026 has already been
inspected and is explicitly development data. Do not select the profitable side
of the earlier constant-exposure scenario as a trading rule.

Protocol, fixed before this experiment's results:

- At odd UTC hours, at :01, compare the just-closed :00 candle's close with the
  close 60 minutes earlier. Score is 10,000 times the natural log price ratio.
- If absolute momentum is at least 20 log-bps, take its direction; otherwise stay flat.
- Reference entry is the :02 candle open, a full minute after the decision.
- Reference exit is 60 minutes after entry. Decisions are two hours apart, so
  positions cannot overlap. Quantity is +0.05 or -0.05 ETH.
- Use hypothetical 5-bps fees and 2-bps combined spread/slippage per side. These
  are not verified account fees or actual fills. The momentum threshold is not
  a forecast, confidence bound or expected-return cost gate.
- Audit the existing trade, funding and mark data before evaluation, then recheck
  hashes. Missing held-period marks or ambiguous funding boundaries fail the run.
- Candidates without a complete end-of-recording window are counted and excluded.
  Their outcomes are unknown, not zero.

```bash
python -u research_usdm_momentum.py \
  --first-pilot data/usdm-pilot-20260801 \
  --batch-root data/usdm-aug02-07 \
  --spot-root data/market-expanded \
  --funding-dir data/usdm-funding-aug01-07 \
  --marks-first data/usdm-marks-20260801 \
  --marks-batch data/usdm-marks-aug02-07 \
  --output data/usdm-UM01-development.json
```

The report retains signals, reference prices, component costs, funding, the
continuous P&L path, sampled drawdown and best-trade removal sensitivity. Outputs
cannot overwrite earlier reports. There is no capital allocation, leverage,
liquidation, contract-filter or execution simulation. Funding completeness remains
unverified. One week cannot establish robustness; even a positive result remains
unapproved. Preserve failures rather than changing parameters until this week wins.
Tests establish signal timing, future-price invariance, long/short/no-signal cases,
coverage rejection, boundary exclusions and integration with accounting.
