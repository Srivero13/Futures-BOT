# Explicit two-leg cost accounting

`basis_cost_accounting.py` evaluates a supplied hypothetical round trip with one
spot leg and one USD-M futures leg of equal ETH quantity. It does not collect
quotes, pick a strategy, check account fees or place orders.

Run the synthetic arithmetic control:

```bash
.venv/bin/python basis_cost_accounting.py \
  --scenario examples/basis-flat-cost-control.json \
  --output data/basis-flat-cost-control.json
```

The control uses invented flat prices of 100, zero spread/slippage, one ETH per
leg, 10 bps per spot execution and 5 bps per futures execution. Expected fees are
0.30 quote units and subtotal -30 bps of entry spot notional. These rates are
explicit hypothetical assumptions, not current or historical account fees.

Scenario inputs must use decimal strings for prices, ETH quantity and rates.
Each venue supplies entry/exit bid/ask, fee rate and adverse slippage rate per
execution. Cost provenance is mandatory. Both directions are supported. Rates
are nonnegative and below 10,000 bps; negative maker rebates are not modeled.

Buys use ask increased by assumed slippage; sells use bid reduced by slippage.
Fees use quantity times each assumed fill times that venue's fee rate. Reference
P&L already crosses bid/ask spreads. Output separates reference price P&L,
slippage, fees and the subtotal before funding/financing. The remaining budget
for omitted costs equals that subtotal, which can be negative. Bps divide by
entry spot midpoint times ETH quantity, not total capital or both legs' notionals.

Funding, borrow, financing, simultaneous execution, liquidity, margin,
liquidation, exchange filters and rounding remain unmodeled. Short spot requires
inventory or borrowing. A positive subtotal never advances a strategy by itself.
For a real hypothesis, supply supportable prices/rates and resolve these omitted
components before proposing a prospective evaluation. Do not reinterpret the
flat control as a replay of the basis pilot or extrapolate its P&L to a portfolio.

## Applying a scenario to recorded quotes

`diagnose_basis_costs.py` reruns the raw capture audit and the existing fixed
anchor selection, then applies this accounting to the same complete anchors at
all four horizons. It saves the unchanged reference diagnostic alongside the
cost scenario and checks input hashes after analysis. It never chooses anchors
based on their prices, cost or direction. A callback added to the anchor runner
exposes complete quote pairs without changing default selection or output.

```bash
.venv/bin/python -u diagnose_basis_costs.py \
  --capture CAPTURE --spot-fee-bps 10 --futures-fee-bps 5 \
  --slippage-bps 0 --output CAPTURE/basis-cost-scenario.json
```

All three rate flags are mandatory decimal values. The example is an explicit
hypothetical sensitivity, not verified account pricing. Zero assumed slippage
is an optimistic scenario, not a claim of zero real slippage. Funding and
financing remain excluded. Do not label the subtotal actual net profit. Exact
fees depend on the four assumed fill prices; the flat-price -30 bps control is
not mechanically subtracted from every recorded observation.

This uses already collected pilot data and does not reopen the closed study,
select a strategy or require further capture. Outputs must be new files.
