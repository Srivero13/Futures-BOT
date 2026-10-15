# Basis quote pilot review — 2026-10-15 UTC

Status: diagnostic completed; no trading candidate advanced. Approved: false.

## Evidence and provenance

These are operator-pasted results, not independently recomputed here from raw
captures. The completed batch is `data/basis-validation-20261015T025504Z`, with
three consecutive five-minute captures. Each supplied horizon has four complete
anchors per capture, twelve pooled. The one-second description and replay checks
are data diagnostics, not independent return observations.

The supplied change-report runner hash is
`18c5e6dc27cd2d2b40ef109d9443110e4557695a4eda3b26b416a9010c6763f0`.
The terminal pooling script checked matching protocol, units and code hashes;
it did not independently rerun accounting or validate input hashes. Preserve
capture folders, protocols, summaries and reports. No private market data is
added to this repository.

## All predefined results

Arithmetic basis points of entry spot midpoint, hypothetical equal one-ETH legs;
includes observed spread crossings but excludes fees and other execution costs.
Means below are rounded terminal values. Positive counts describe references,
not successful trades.

| Horizon | Long futures / short spot mean | Positive | Long spot / short futures mean | Positive |
|---|---:|---:|---:|---:|
| 5 seconds | +0.04975 | 6/12 | -0.28465 | 3/12 |
| 15 seconds | +0.31687 | 6/12 | -0.50986 | 3/12 |
| 30 seconds | +0.81069 | 10/12 | -1.02123 | 1/12 |
| 60 seconds | -0.02768 | 5/12 | -0.16886 | 5/12 |

The largest reported mean is a descriptive maximum across eight results, not a
selected strategy. Do not freeze the 30-second long-futures direction after
seeing this table and call these same observations validation.

## Interpretation

An average futures discount is a price level, not an attainable return. A static
discount loses spread crossings in the two-leg quote-change calculation. The
largest mean here leaves only approximately 0.81 bps of reference notional for
ALL omitted costs. Dividing by four executions gives approximately 0.20 bps per
execution only under equal-notional, equal-cost assumptions. This is an arithmetic
illustration, not an account fee quote or a feasibility claim; exact fees use
each leg's actual execution notional. Borrowing, funding, slippage, asynchronous
quotes and legging remain additional issues. No profitability is established.

Twelve anchors in one short session do not establish significance, persistence,
market-regime coverage or sufficient order capacity. These results also do not
prove all possible basis strategies are unprofitable.

## Disposition and work boundary

The capture/replay pipeline has completed its bounded live pilot. It remains an
observation tool, not an unattended trading system. Stop the current repetition
of short captures and do not extend training or tune directions/horizons from
these results. No model promotion, live order path or reserved historical data
access follows from this review.

Reopening a basis strategy study requires a documented economic hypothesis with
an all-in cost model for both markets, feasible inventory/borrowing assumptions,
execution-latency treatment and a predeclared prospective evaluation. If those
conditions cannot plausibly fit the expected effect, do not spend more collection
or GPU time on that hypothesis. This review closes the diagnostic task; it does
not claim the overall trading-bot goal is complete.
