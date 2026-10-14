# Funding cash-flow arithmetic

The diagnostic reaudits the saved week and reports funding for two separate,
hypothetical exposures: +1 ETH and -1 ETH at every recorded ETHUSDT event.
It does not select a side, create trades or compute strategy P&L.

```bash
python diagnose_funding_cashflows.py \
  --funding-dir data/usdm-funding-aug01-07 \
  --symbol ETHUSDT --start 2026-08-01 --end 2026-08-08 \
  --reserve-from 2026-09-01 \
  --output data/usdm-funding-cashflows-aug01-07.json
```

For signed base quantity q, settlement mark M and rate r, account cash flow is
`-q * M * r`. Positive cash means receipt. Positive rates debit longs and credit
shorts; negative rates reverse the direction. The helper uses decimal inputs
with 50-digit calculation precision; it rejects floats, nonfinite inputs and
missing/nonpositive marks. Exchange-specific cash rounding is not implemented.
ETHUSDT figures are denominated in USDT. Equal opposite positions balance before
rounding. No leverage factor is applied to an already specified quantity.

The report retains each original timestamp, rate, mark, and both cash flows.
It verifies input hashes again after calculation. Totals describe only the
recorded events and assumed exposures, not a recommended position or profit.
Price movements, trading costs, liquidation and historical schedule completeness
remain outside this calculation.

## Boundary policy for later integration

The standalone `event_exposure` helper classifies an event as held, not held or
ambiguous. Entry or exit within 60 seconds of the event is ambiguous, including
exact equality. This is a conservative research guard, not a verified exchange
settlement window or a guarantee outside that window. It is not used to invent
entries/exits in the unit-exposure report. A later backtest must surface ambiguous
payments instead of assigning zero or silently dropping the position. No actual
ledger or trading strategy is wired to this helper yet.

[Binance funding documentation](https://www.binance.com/en-NZ/support/faq/detail/360033525031)
explains position value, payment direction and settlement-time uncertainty.
This current documentation does not independently certify historical rules for
the development interval.

Four tests cover direction, zero exposure/rates, invalid numbers, boundary
ambiguity and a complete synthetic audited week whose long and short totals
reconcile. Actual operator totals have not been computed in this workspace.
