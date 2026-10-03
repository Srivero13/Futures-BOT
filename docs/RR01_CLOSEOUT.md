# RR-01 closeout: no candidate promoted

Decision date: October 3, 2026 (America/La_Paz). Retire the fixed
BTC-conditioned ETH recovery configuration. All four predefined development
screens failed. The original protocol and implementation remain available for
reproduction; this is not an invitation to tune the failed configuration.

## Evidence

The operator ran the fixed protocol committed in
f760f235b4d1b97a6c5f7ca98f1a5fea2a2f085b and supplied the console summary.
These figures have not been independently reproduced on market data in the
repository workspace. Preserve the full local report and protocol.

| Metric | Result |
| --- | ---: |
| Completed trades | 23 |
| Profitable months | 2 of 6 |
| Sum of independent-month net P&L | −5.523911658465759 USDT |
| Net P&L excluding best trade | −6.710571911284839 USDT |
| Net P&L with extra 1 bps slippage per side | −5.983815402591012 USDT |
| Fees | 4.599037759638759 USDT |
| Assumed spread/slippage cost | 1.379711368827 USDT |
| Derived reference-price gross P&L | +0.454837470000000 USDT |

The monthly cash balances reset independently. These sums are not a compounded
six-month portfolio return. Cost stress and the cost-removal calculations below
hold trade timing and quantity fixed.

The derived reference-price gross result is net P&L plus fees plus modeled
price impact. It describes the selected price moves before these costs; it is
not a feasible zero-cost trading result. Removing fees alone, while retaining
the original modeled price impact, leaves **−0.924873898827 USDT**. This run
does not justify a fee-discount-based rescue, longer training, or GPU expansion.

## Decision and research history

The rule had some favorable price moves, but sparse trades and a very small
aggregate gross surplus do not support an economically useful selection rule.
No significance test is claimed. A failed fixed experiment does not prove that
all relative-value mechanisms fail.

RR-01 adds a failure to the existing research history; it does not replace the
[earlier development closeout](DEVELOPMENT_PHASE_CLOSEOUT.md). The cost-opportunity
audit remains descriptive: its 11.27% and 23.54% cost-exceeding frequencies were
not evidence that this rule could identify those observations.

Disposition:

- No threshold, holding-period, sign, fee, or feature changes to rescue RR-01.
- No September-or-later evaluation for this rejected configuration.
- No promotion to paper/live strategy execution.
- Preserve raw data and reports; do not relabel inspected development months as
  unseen evaluation data.
- Any distinct future experiment needs its own mechanism, fixed budget,
  benchmarks and written protocol before outcomes are inspected.

The [machine-readable decision](../reports/development/rr01-closeout.json)
records the monthly results, evidence origin, and derived accounting. It is a
research record, not a runtime enforcement mechanism.

Local evidence:

```text
data/eth-relative-recovery-development.json
data/eth-relative-recovery-development.protocol.json
```
