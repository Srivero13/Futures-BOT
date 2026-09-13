# Our results — v0.2

**Result: insufficient evidence to trade real money with these strategies.**

These are historical simulations, not real trades or forecasts. Fixed universe: BTCUSDT and ETHUSDT. Period: January–March 2025, 25,920 five-minute candles per symbol (51,840 total), downloaded from the official Binance archive and verified against its checksums. The chosen quarter is a reproducible pilot study, not a representation of every regime or the current market.

Protocol fixed before viewing results: select the highest January PnL among SMA 5/20, 12/48 with 26 bps separation, and 20/60 with 26 bps separation. Validate in February and evaluate in March without reselection. Both symbols selected SMA 20/60. Windows refer to five-minute bars (100 and 300 minutes); this is not second-scale scalping. The separation parameter is not a profit forecast.

Each evaluation starts with 1,000 virtual USDT and a single position of up to 100 USDT, without leverage or proportional reinvestment. Maximum 12 entries per UTC day, a three-bar cooldown after exit, a halt after 5% peak drawdown, and a daily pause after a 2% loss. Signals precede the opening; fills occur at the next opening with impact. Risk exits occur on the next observation, not through an intrabar stop.

Hypothetical base costs: 10 bps fees per side, 2 bps full spread, and 2 bps slippage per side. These are not confirmed account fees. A 0.000001 quantity step and 5 USDT minimum notional are laboratory parameters, not all historical Binance filters. Electricity and taxes are excluded.

## February validation

| Pair | Net PnL USDT | Closed trades | Maximum account drawdown |
|---|---:|---:|---:|
| BTCUSDT | -13.765246 | 49 | 2.414% |
| ETHUSDT | -26.208131 | 67 | 3.135% |

## Final evaluation: March, 744 hours

| Pair | Strategy/cost | Net PnL USDT | Fees USDT | Trades | Maximum account drawdown |
|---|---|---:|---:|---:|---:|
| BTCUSDT | baseline_5_20 | -43.585497 | 41.3812 | 207 | 5.002% |
| BTCUSDT | selected | -12.801949 | 13.1952 | 66 | 1.978% |
| BTCUSDT | buy_hold_100 | -2.390039 | 0.1978 | 1 | 2.109% |
| BTCUSDT | cash | 0.000000 | 0.0000 | 0 | 0.000% |
| BTCUSDT | selected_cost_zero | 4.350947 | 0.0000 | 66 | 0.961% |
| BTCUSDT | selected_fee_7_5 | -9.503141 | 9.8964 | 66 | 1.723% |
| BTCUSDT | selected_stress | -28.617769 | 19.7785 | 66 | 3.207% |
| ETHUSDT | baseline_5_20 | -39.392721 | 28.1885 | 141 | 5.015% |
| ETHUSDT | selected | 0.002963 | 13.0129 | 65 | 1.328% |
| ETHUSDT | buy_hold_100 | -18.783915 | 0.1814 | 1 | 3.371% |
| ETHUSDT | cash | 0.000000 | 0.0000 | 0 | 0.000% |
| ETHUSDT | selected_cost_zero | 16.924933 | 0.0000 | 65 | 0.887% |
| ETHUSDT | selected_fee_7_5 | 3.256186 | 9.7597 | 65 | 1.159% |
| ETHUSDT | selected_stress | -15.601633 | 19.5056 | 65 | 2.510% |

The 5/20 baseline permits up to 288 entries/day without cooldown, with the same loss limits. It adapts the v0.1 idea to candles rather than reproducing five-second intervals. `buy_hold_100` buys up to 100 USDT and holds the remainder in cash, without stops or rebalancing. `selected_cost_zero` removes fees and impact; `selected_fee_7_5` reduces fees only to 7.5 bps; `selected_stress` uses 15 bps fees, 5 bps slippage, and 10 bps spread. Parameters are not reoptimized.

## Gains and losses per hour/second

| Pair, selected strategy | Average USDT/h | Arithmetic average USDT/s | Worst hour USDT | Best hour USDT | Win rate | Profit factor |
|---|---:|---:|---:|---:|---:|---:|
| BTCUSDT | -0.017206921 | -0.000004779700 | -3.8027 | 3.6903 | 25.76% | 0.6018 |
| ETHUSDT | 0.000003982 | 0.000000001106 | -2.2549 | 7.6060 | 32.31% | 1.0001 |

Hours are grouped in UTC and include equity changes from open positions. Closed-trade profits are recorded separately. All inventory is liquidated at the end with exit costs, reconciling total PnL with realized trades. The per-second average does NOT measure execution or intrasecond extremes. Averages include all 744 hours, including periods without exposure.

ETH ended with only a few thousandths of a USDT in profit: economically indistinguishable from zero for this use, and additional costs make it negative. BTC moved from profit without costs to net loss. Stress loses on both symbols. Losing less than the baseline is not interpreted as a positive edge.

## Two simultaneous accounts

Total virtual capital: 2,000 USDT. Combined PnL: -12.798987 USDT. Maximum combined close-marked drawdown: 1.503%. This aggregates two independent accounts; it is NOT an implemented global risk limit.

## Measured requirements

The full benchmark took 86.15 seconds in the development environment, with peak Python allocations of 25.60 MiB measured using tracemalloc. This is NOT total process RAM or a measurement of the user's i7; instrumentation adds overhead. It cannot establish trading latency. No GPU or external packages are used.

## Limitations and reproducibility

CSVs and hashes are included. `python3 benchmark.py` reproduces the tables; `python3 make_report.py` updates this report. No AI model was used and parameters were not adjusted to March results. Only historical periods were reserved, not genuinely unseen future data. Repeated tuning against March would turn it into training data.

Missing elements include depth, maker queues, variable latency, partial fills, historical spread, exact historical filters, delistings, account-specific fees, other quarters, and demo validation. Drawdown observed at openings/closings may underestimate intrabar drawdown; there is no guaranteed stop. One quarter and two symbols cannot establish the probability of future profitability.

Full results are in `results/comparison.csv`, `selection.json`, and directories containing `summary.json`, `trades.csv`, `hourly.csv`, and `equity.csv`. Other-bot research and references are in `research/ANALYSIS.md`.
