# WBC01 — fixed weekly Bitcoin control, protocol only

No result exists and no strategy is approved. This is a slower-horizon research
control for the overall project, not a completed scalping bot or a deployment
recommendation. Machine-readable constants are in
`research_protocols/weekly_btc_control_v1.json`.

## Motivation and distinction

Liu and Tsyvinski, *Risks and Returns of Cryptocurrency*, NBER working paper
24877 (2018), section 4.1, reports historical Bitcoin weekly momentum:
https://www.nber.org/papers/w24877.pdf . Retrieved indexed primary-source text on
2026-10-15. That historical finding motivates a falsifiable hypothesis; it does
not certify modern returns after costs. The sign rule below is our operational
control, not a replication of the paper's regression or portfolio construction.

Hypothesis: weekly directional persistence may support a lower-turnover,
single-market exposure after costs. Previous project rules used minute/hour
momentum or channel breakouts; this does not erase their failures. Longer holding
also increases exposure to adverse moves. There is no evidence yet that the
expected effect exceeds costs, and no guarantee of earning an edge.

## Fixed causal rule

- BTCUSDT spot only. Long or cash, never short or leveraged; no futures funding
  or two-market legging. No GPU model, features, filters or fitted thresholds.
- On each Monday at 00:00 UTC compare the immediately preceding Sunday 23:59
  one-minute candle close with the close exactly seven days earlier. Both
  candles must be completed. Strictly positive change targets long; zero or
  negative targets cash. Validate all intervening minute coverage; do not fill
  missing data or aggregate incomplete weeks.
- Entry/exit reference is Monday 00:01 UTC candle open, one minute after the
  decision. Do not fill at the candle that generated the signal.
- Starting cash 1000 USDT. On a cash-to-long transition spend at most 100 USDT
  INCLUDING entry fee, using price increased by 2 bps impact and 10 bps fee.
  Keep the resulting BTC quantity until a long-to-cash transition. No weekly
  rebalance or repeat fee while the target is unchanged. A sale uses reference
  price reduced by 2 bps impact and a 10 bps fee on the resulting proceeds.
- Preserve cash, quantity and equity continuously across months. No monthly
  resets, reentry optimization, stop-loss search or direction inversion.
- Development decisions begin 2024-01-08, with required prior data for warmup.
  No price or label at/after 2026-09-01 may be read. Close remaining exposure at
  the predeclared 2026-08-31 23:59 UTC open, applying exit costs; disclose it as
  forced terminal liquidation. This is a research reference fill, not observed
  execution. Prior dataset/model usage makes this entire run development data.

## Required report and comparisons

Record input hashes, code/protocol hashes, every decision and trade, turnover,
fee/impact components, invested time, continuous daily equity, drawdown, annual
and calendar-quarter results. Label references as simulated and preserve failed
runs. Unknown exchange filters/rounding and actual fills remain limitations.

Compare cash (zero interest) and a 100-USDT-entry-budget buy-and-hold position
from the first scheduled execution to the same terminal liquidation, with the
same fees and impact. Show both return and exposure/drawdown; neither comparison
alone establishes risk-adjusted alpha. Do not compare different capital bases.

The sole stress rerun adds 1 bps adverse impact per execution with the same
signal schedule. Recompute affordable entry quantities and fees from the same
100-USDT entry budget; do not relabel a fixed-quantity stress as a full rerun.
Report removal of the best completed trade as arithmetic sensitivity, not an
executable alternative path. Include the forced terminal trade in totals and
identify it separately.

## Finite decision rule and data boundary

One configuration plus the stated stress, no search. To justify even designing
an independent evaluation, require positive development subtotal after costs,
positive stressed result, positive arithmetic best-trade-removal result and at
least 30 completed round trips. Otherwise reject or mark insufficient evidence;
do not relax thresholds, change the horizon or switch assets after inspecting
outcomes. These are engineering screening choices, not significance guarantees.
A candidate satisfying them remains unapproved; report cash/buy-and-hold results
and drawdowns without cherry-picking. Full independent evaluation criteria and
an actually uninspected chronological period must be documented separately
before any such data are accessed. No September data is authorized by this file.

Protocol was frozen before implementation and WBC01 calculations. No market results have been run here,
no downloads started and no live trading path enabled.

## Implementation and operator run

`research_weekly_btc.py` now implements this fixed protocol. Its protocol hash is
pinned: editing the JSON cannot silently change the experiment. Provenance checks
require Binance BTCUSDT one-minute shards with matching local hashes and ranges
before the reserve. Every minute from 2023-12-31 23:59 UTC through the terminal
reference must exist exactly once. The input files remain previously used
research data; downloaded warmup does not make the evaluation independent.

```bash
.venv/bin/python download_v15_data.py --source binance --symbol BTCUSDT \
  --start 2023-12-01 --end 2024-01-01 --root data/market-expanded &&
.venv/bin/python -u research_weekly_btc.py \
  --files data/market-expanded/binance-BTCUSDT-2023-12.csv \
    data/market-expanded/binance-BTCUSDT-2024-*.csv \
    data/market-expanded/binance-BTCUSDT-2025-*.csv \
    data/market-expanded/binance-BTCUSDT-2026-0[1-8].csv \
  --output data/weekly-btc-WBC01-development.json
```

The output preserves decisions, full trades, daily cash/quantity/equity, fees,
impact, turnover and calendar period equity changes for the base/stress and
buy-and-hold cases. Drawdown uses daily sampled equity and terminal liquidation;
it is not an intraday risk bound. Costs are explicit assumptions, and exchange
lot-size rounding is not modeled. Zero cash yield is assumed. Passing a screen
still does not approve trading. The operator's data are not available in CI;
causal fixtures test delayed open fills, missing-minute rejection, no unnecessary
rebalance, affordable stress sizing and component reconciliation.

## Minute reference risk replay

`diagnose_weekly_btc_risk.py` reads the existing report and its recorded source
paths. It verifies source hashes and metadata, rebuilds the unchanged weekly
schedule and all three accounting scenarios, and rejects any saved result that
differs. It then streams every development minute for base, stress and buy-and-hold.
It never accesses September or changes signal thresholds.

```bash
.venv/bin/python -u diagnose_weekly_btc_risk.py \
  --report data/weekly-btc-WBC01-development.json \
  --output data/weekly-btc-WBC01-risk.json
```

Sampled drawdown uses minute opens/closes plus equity immediately before and
after transactions. The OHLC upper bound additionally permits each minute's high
to precede its low. Both carry the portfolio peak across trades. Entry costs apply
before that minute's extrema; an exit at the open excludes subsequent extrema for
the exited position. The initial equity is 1,000 USDT and the entry budget remains
100 USDT. Terminal cash must reconcile to the saved accounting. Output paths must
be new; source reports are not modified.

These are reference-price risk measurements, not executable liquidation equity.
The upper bound covers supplied candles and assumed fills only. Less exposure and
more idle cash can reduce drawdown without establishing superior risk-adjusted
performance. No strategy promotion follows from this diagnostic.

Operator-reported development results: 37 trades, base net 48.2748 USDT, stress
47.5252, buy-and-hold 78.5453, and base excluding the best trade 7.1567. The original
screen passed. Base period changes were +49.0831 in 2024, +5.5699 in 2025 and
-6.3782 in the partial 2026 period; this concentration warrants caution. These
figures were supplied by the operator, not independently run against local data.
