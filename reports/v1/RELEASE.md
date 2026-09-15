# 1.0 report — September 13, 2026

## Decision

This release provides a research/paper engine with more precise accounting and shared controls. Entries are disabled for the included models because there is no evidence of a net edge. Optimal timing for a deployment host cannot honestly be selected without measurements there and subminute execution validation using order-book data.

## Measured response

Development environment, not the user's PC. Two series of 30 public REST requests:

| Endpoint | Successes / attempts | Failures | Successful-response p50 | Successful-response p95/p99 |
|---|---:|---:|---:|---:|
| Binance server time | 5 / 30 | 25 | 1831.89 ms | 3295.17 ms |
| BTC best bid/ask | 3 / 30 | 27 | 3407.80 ms | 3506.67 ms |

Percentiles from three or five successes are unreliable tail estimates and exclude failed requests. The profile is **rejected**; tolerances are not widened to accept a poor connection. The urllib timeout applies per socket operation and does not guarantee a two-second total deadline. No order acknowledgments or fills were measured.

WebSocket observation received 2,230 messages in 30.00 seconds, with one reconnection caused by `WebSocketProxyException`. The p95 between receptions was 53.39 ms: this is interarrival time, **not RTT or execution latency**. This observation provided no valid event-lag or order-computation measurement. Raw data: `latency-development.json` and `stream-development.json`.

Chosen rules: a current local profile, ≥30 successes per endpoint, failures ≤5%, p99 ≤1000 ms, and clock uncertainty ≤250 ms; decision spacing at least `max(100, 2 p95)` ms, maximum receipt age `min(1000, max(250, 3 p99))` ms, and horizon at least `max(60000, 20 p99)` ms. These parameters are not profit-optimized. New entries are blocked when the profile expires during a session.

Binance spot bookTicker publishes best prices/quantities in real time but lacks event timestamp E: local receipt age cannot prove source freshness. The candle stream permits closure and lag checks; gaps require warmup. The library handles ping/pong and the client reconnects. Reference: [official WebSocket documentation](https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md).

`recvWindow` determines temporal validity of signed requests; it is not a latency target or a reason to poll every 5000 ms. This version does not sign requests. [Official REST documentation](https://developers.binance.com/en/docs/products/spot/rest-api).

## Mathematical model

Accounting accepts decimal strings, rejects float/NaN/infinity, and uses precision 50. Quantities round down to the permitted step; fees and slippage apply to both entry and exit. [Python Decimal](https://docs.python.org/3/library/decimal.html). More digits do not improve market prediction.

For ask A, bid B, proportional fee f, and slippage s, the minimum bid growth needed to recover costs is:

`c = A (1+s) (1+f) / [B (1-s) (1-f)] - 1`.

The label is log return from the opening after the signal candle to the opening h minutes later: `y = 10000 ln(P_exit / P_entry)`. The forecast minus an error buffer is compared with `10000 ln(1+c) + 2` log bps; simple and log returns are not mixed. Future labels never enter indicator calculations.

Ridge uses one-minute return, 5/20 momentum, 20-period volatility, relative volume, and candle range. Normalization uses fitting data only; coefficients use augmented least squares with L2 regularization (alpha 10), solved by SVD without inverting X'X. [Official Ridge definition](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html). Statistics use float64; money uses Decimal.

Calibration estimates the one-sided 90th percentile of overprediction error, using samples h minutes apart. This is neither a probability of profit nor a coverage guarantee under temporal dependence. Inputs more than eight training standard deviations away are rejected. Scaling, horizon selection, and temporal validation remain separate; labels crossing boundaries are purged. [Temporal splitting with a gap](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html).

## Protocol and results

Official BTC/ETH spot data: 131,040 one-minute candles per symbol, April–June 2025. April: 80% fitting and 20% calibration. May: compare 1-, 3-, and 5-minute horizons. June: subsequent evaluation without refitting. File manifest and SHA-256 are in `datasets/manifest-v1.json`; download with `download_v1_data.py`.

All three horizons tied in May without trades. The artifact retains one minute by tie-breaking order, **not because it is the best timing**. Promotion requires positive May net profit, at least 30 closed trades, and calibration RMSE below a zero forecast; these conditions fail. The historical models are also expired for current paper trading.

In June the models do not trade under 50, 250, or 1000 ms scenarios, including increased costs. Net result and fees: zero. This is abstention, not evidence of profitability or predictive improvement over the previous version. The momentum reference, with the same limits, loses approximately 50.18 USDT for BTC and 50.14 for ETH per virtual 1,000; drawdown blocks it. This is not a direct comparison with the v0.2 strategy, which used a different period/frequency.

Assumed base fees are 10 bps per side, slippage 2 bps, and spread 2 bps; stress uses 15/5/10. Previous volatility multiplied by the square root of time widens the spread in latency scenarios: this is synthetic sensitivity, not reconstructed execution. Full fills, abundant synthetic liquidity, and no queue modeling limit the study. Electricity, taxes, funding, and futures costs are excluded. Observed per-second PnL cannot be extracted from one-minute candles; only a normalized per-second average and aggregated hourly PnL are supplied.

In the base scenario, signal-computation p99 was 0.03194 ms for BTC and 0.04282 ms for ETH. This measures inference only, excluding network reads, SQLite, order submission, and execution. Calibration RMSE (BTC 4.52961 and ETH 8.05565 log bps) was slightly worse than predicting zero (4.52302 and 8.04770).

See `evaluation.json` for exact figures, per-case metrics, RMSE, and computation timings from this environment. Detailed logs are regenerated with `train_v1.py`. These are historical data, not a diagnosis of the September 2026 market.

## Validation and scope

43 automated tests, including 21 previous and 22 new tests: exact accounting, break-even cost, quantization, restart/idempotency, global cap, second-account blocking after costs, stale/future quote rejection, rollback, persistent drawdown, per-account horizon, model integrity, causality, and holdout separation. The previous suite's demo authentication test uses mocks and does not demonstrate private-account connectivity.

A short public WebSocket connection was verified. Continuous operation, deployment-specific hardware and networks, and Windows were not validated. Two virtual ledgers are not two authenticated exchange accounts. There is no real-order submission path. Financial execution development requires a validated strategy, subminute data, testnet testing, and robust reconciliation. The 1.0 label identifies this software release; it does not certify suitability for real capital.
