# Audit and evidence — Rivero Bots v0.2

Prepared for Santiago Rivero. Sources consulted on September 12, 2026. This document describes the v0.2 release.

## Assessment of v0.1

Version 0.1 was an infrastructure experiment. There was no evidence to call it profitable, AI-powered, or a validated scalper. Passing ten tests does not demonstrate a market edge. A sinusoidal series tests buys and sells but does not represent market uncertainty. Local operation does not demonstrate connectivity to two real accounts.

| Finding | Consequence | v0.2 change |
|---|---|---|
| Averages of observations rather than closed candles | Depend on polling frequency | New causal historical engine using 5m candles |
| Signal and execution on the same observation | Overly optimistic execution | Previous signal; next candle opening plus costs |
| No historical data or reserved period | Generalization cannot be evaluated | January selection, February validation, March final evaluation |
| No passive reference | Gains may be due solely to market direction | Cash and buy-and-hold with equal initial allocation |
| Loss measured from initial capital, without day or peak | Does not cover losses after earlier gains | Historical engine adds daily loss and peak-based drawdown |
| Sample history lost on restart | Signals change after restart | Atomic persistence of the last 20 paper-engine samples |
| No hourly or realized/unrealized metrics | Incomplete or unclear PnL | Historical exports and paper-ledger reporting |
| Float accounting | Insufficient foundation for financial execution | New backtester uses Decimal; inherited paper engine remains float |
| Slow quote responses accepted | May simulate using delayed data | Reject responses over five seconds; exchange-side data age remains unchecked |
| Simulator does not reproduce CFDs or forex | Transferring results would be incorrect | Explicit economic scope: Binance spot, long-only, no leverage |

`bot.py` retains the v0.1 concurrent laboratory with persistence and delay corrections. `backtest.py` is a separate research engine: its risk rules are not presented as integrated into the online engine. Equivalence has not been demonstrated. Capital demo remains an account query, not execution.

## Other bots: available evidence

### Hummingbot on Binance: published results, not audited by us

The foundation published a 48-hour competition in September 2023 with five eligible participants and less than 100 USDT initial capital per participant. The table reports their PnL; the last two columns are our arithmetic divisions:

| Participant | Market | Reported PnL (USDT/48h) | Average USDT/h | Average USDT/s |
|---|---|---:|---:|---:|
| doi_doi | Binance perpetuals | +134.72 | +2.806667 | +0.00077963 |
| WeGotGame | Binance perpetuals | +11.24 | +0.234167 | +0.00006505 |
| nikita7970 | Binance perpetuals | −5.40 | −0.112500 | −0.00003125 |
| fengtality | Binance spot | −1.00 | −0.020833 | −0.00000579 |
| cgambit | Binance spot | −3.61 | −0.075208 | −0.00002089 |

Primary source: [Hummingbot results](https://hummingbot.org/blog/-beta-bot-battle-results-and-roundup/).

The table does not establish per-second distribution, complete drawdown, or a long track record. Participation bias and excluded data apply. Futures results are not comparable with our unleveraged spot simulation. Winners are not annualized or extrapolated to the user's capital. These are not expected Hummingbot returns.

### Binance Spot Grid

Binance distinguishes profit on matched trades from unrealized inventory: a grid can show closed-cycle profits while losing overall. Therefore v0.2 retains inventory valuation and forces final backtest liquidation with costs. We found no audited population-level return that would justify assigning an hourly income to the product. [Official parameters](https://www.binance.com/en/support/faq/detail/688ff6ff08734848915de76a07b953dd).

### Freqtrade

Freqtrade provides infrastructure for custom strategies, not a rate of return. Its documentation recommends at least 2 vCPU, 2 GB RAM, 1 GB disk, and a synchronized clock. An i7/16 GB exceeds that minimum for modest workloads, though large historical datasets and intensive searches require more resources. [Official repository](https://github.com/freqtrade/freqtrade).

Its tools warn about future-candle lookahead and differences between backtesting and execution. We adopted temporal separation and a test that changes the future while checking that the past stays unchanged. We did not run Freqtrade or Hummingbot or replicate their strategies: our results belong exclusively to our engine. [Lookahead](https://www.freqtrade.io/en/stable/lookahead-analysis/) · [Backtesting](https://www.freqtrade.io/en/stable/backtesting/).

## Market studies

**Hudson and Urquhart, Technical trading and cryptocurrencies, Annals of Operations Research.** Examines 14,919 rules using daily data and multiple-testing adjustments. Some analyses find favorable results, but Bitcoin does not retain out-of-sample predictability. This supports reserving data and controlling selection; it does not prove profitable Binance scalping. [Article](https://link.springer.com/article/10.1007/s10479-019-03357-1).

**Bysik and Ślepaczuk, 2026 preprint, Machine Learning-Based Bitcoin Trading Under Transaction Costs.** The abstract describes approximately 70,000 hourly observations and 27 validation windows. Naive strategies fail under ten-basis-point costs; some filtered configurations improve, and one XGBoost configuration exceeds 65% annualized in the experiment. This is not a real-money track record, was not replicated by us, and is not transferred to this bot. Reading was limited to the preprint abstract. [arXiv](https://arxiv.org/abs/2606.00060).

**Inference for our design:** before adding a neural network, check whether signals overcome costs and survive reserved data. This evidence does not justify buying a GPU or claiming that complex AI will outperform a small model. The v0.2 moving-average separation filter does NOT predict returns or guarantee cost recovery; it is a hypothesis being tested.

## Gains and losses per second and hour

There is no fixed income. Required inputs include capital, trade size, completed trades, average gain/loss, fees, and temporal distribution. A per-second average is PnL divided by seconds; it does not mean a trade every second or a steady flow. Our 5m candles cannot measure intrasecond extremes.

Purely hypothetical example: 100 USDT notional, 0.10% fee on each side, 0.02% full spread, and 0.02% slippage per side. Approximate round-trip cost: 0.26 USDT. These are not confirmed account fees. Exact cost changes with exit price.

| Gross favorable movement per cycle | Approximate net PnL/cycle | If 10 identical cycles completed per hour |
|---|---:|---:|
| 0.10% | −0.16 USDT | −1.60 USDT/h |
| 0.30% | +0.04 USDT | +0.40 USDT/h |
| −0.30% | −0.56 USDT | −5.60 USDT/h |

These rows are NOT predictions or probabilities. They assume identical movements in every cycle. Break-even must include both executions; more cycles without an edge mean greater cost losses.

Electricity: hourly cost = measured watts / 1000 × price per kWh. Convert to backtest currency before using `--overhead-hour`. Actual power, marginal tariff, and applicable conversion are unknown. Delivered results exclude electricity, taxes, and deposits/withdrawals; they include simulated trading costs.

## Remaining problems and priorities

| Risk | Effect | Treatment |
|---|---|---|
| Account-specific fees/promotions | Gross profitability may become net loss | Cost scenarios; confirm account fees before trading |
| Variable spread/slippage | Erodes small margins | Stress included; historical order book pending |
| Partial fills/maker queue | A signal is not a filled order | Not modeled yet; do not send real orders |
| Pair and period selection | BTC/ETH Q1 does not represent the whole market | Expand periods and regimes before approving a strategy |
| Two correlated bots | Duplicate crypto exposure | Show capital per account; global cap still pending in v0.2 |
| Power/internet failure and restart | Unsupervised positions | Local persistence; real reconciliation and supervisor missing |
| Price gaps | Loss exceeds stop | Explicit test; limit is not guaranteed |
| API limits and symbol filters | Rejections, bans, or invalid sizes | Laboratory rounding/min_notional; actual filter loading missing |
| Overfitting | Past winners fail later | Three predefined candidates and a reserved period |
| Confusing spot with futures/CFDs | Margin, financing, and liquidation risks | Excluded from benchmark; require separate models |

Official filters include price, quantity, and notional limits: [Binance filters](https://developers.binance.com/docs/binance-spot-api-docs/filters). A generic decimal step in a backtest does not replace all filters. APIs also impose limits: [Binance REST](https://developers.binance.com/docs/binance-spot-api-docs/rest-api/limits).

## Technical decision

Keep Ubuntu and Python, two small processes, and SSD storage. Additional hardware is not justified for this scope without measurement. Judge v0.2 by its ability to detect and document poor strategies, not by forcing a positive result. It includes neither trained AI nor real execution. Later operational integration should share a validated decision engine and add reconciliation, global limits, order state, and prolonged demo testing.
