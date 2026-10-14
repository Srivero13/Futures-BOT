# Fixed-time futures round-trip accounting

This is an accounting integration scenario, not a trading strategy. The fixed
week has already been inspected. No performance claim or unseen evaluation is
possible from this run.

```bash
python -u diagnose_usdm_roundtrip.py \
  --first-pilot data/usdm-pilot-20260801 \
  --batch-root data/usdm-aug02-07 \
  --spot-root data/market-expanded \
  --funding-dir data/usdm-funding-aug01-07 \
  --fee-bps 5 --impact-bps 2 \
  --output data/usdm-roundtrip-aug01-07.json
```

The example costs are explicit hypothetical assumptions: 5 bps fee and 2 bps
combined spread/slippage per side. They are not the user's verified futures
fees or an exchange fee quote. Both costs apply on entry and exit. Do not infer
that they are sufficiently conservative without execution evidence.

The scenario uses one ETH, separately long and short, entering August 1 00:02 UTC
and exiting August 7 23:58 UTC. These fixed times are chosen to separate the
accounting fixture from the initial funding boundary, not to optimize returns.
Candle open references are adjusted adversely for impact: long buys higher and
sells lower; short sells lower and buys higher. Fees use actual assumed fill
notional on both sides. Funding uses signed quantity and settlement mark.

Only funding inside the holding window is included. Entry/exit within 60 seconds
of a recorded funding event is ambiguous: the output retains its timestamp and
sets scenario_net_pnl to null. This guard is a research convention, not verified
settlement behavior. Missing marks on held events fail. Supplied events must be
unique and ordered. Data are reaudited and rehashed before reporting.

There is no margin or liquidation model, contract filter, exchange rounding,
mark-price equity curve, signal selection or automatic order placement. Source
funding schedule coverage remains unverified. The integration therefore remains
unapproved even if scenario arithmetic resolves. Favorable fixed-direction P&L
cannot promote a strategy.

Four tests verify adverse costs for each side, funding exposure and missing
marks, ambiguous boundaries, and invalid costs/duplicate events. Synthetic
arithmetic tests passed; market-data results require the operator's run.
