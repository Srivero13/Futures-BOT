# Futures-BOT 1.1 engineering and research audit

## Assessment

Version 1.1 improves operational correctness, research reproducibility, and selected processing costs. It does not establish a profitable trading strategy or a universal percentage improvement. The current economic result remains abstention: no candidate satisfies the promotion requirements across the reported historical folds. The release therefore retains paper-only scope and does not install any newly evaluated historical model for current trading.

The strongest measured improvement is batch feature construction. On identical 10,000-candle inputs, median runtime fell from 132.61 ms to 6.38 ms, approximately 20.8× faster. Numerical equivalence was checked against the exact v1.0 implementation within a relative tolerance of 1e-10 and absolute tolerance of 1e-12. This accelerates research preparation; it is not a 20.8× improvement in market prediction or order execution.

The idle-ledger benchmark reduced post-close database size from 3,252,224 to 491,520 bytes, approximately 84.9%. It removed 10,000 HOLD audit records while preserving state and deduplication. Ledger runtime rose from 0.540 to 0.565 seconds in this workload, approximately 4.6% slower, reflecting additional controls and measurement variability. These are local development measurements, not measurements of other deployment hosts or connections.

## Scope and evidence

The reference implementation is Git commit `58590544fa26f55390baaa41d7aab953e611a094`. Audit evidence combines source inspection, regression and fault tests, the identical-input engineering benchmark, official exchange and database documentation, and a fixed rolling historical experiment. There is no real-money trade record, broker order latency, or demonstrated profitability in this evidence.

The installation workflow targets a Linux host with CPU-based numerical processing. This release introduces no GPU framework. Hardware changes cannot establish predictive edge. No profitability comparison with commercial bots is inferred from marketing figures or a competition leaderboard. Earlier v0.2 literature remains archived; current release conclusions are based on the measurements and sources identified here.

## Audit findings and remedies

| Finding in 1.0 | Consequence | 1.1 treatment | Remaining limit |
|---|---|---|---|
| Any stale held symbol returned before processing accounts | Healthy positions could not exit during another market's outage | Block all entries but process exits using fresh quotes on other symbols | No liquidation price is invented for the stale position |
| Precision depended on ambient Decimal context | Import order or caller settings could alter arithmetic | Monetary operations use an isolated 50-digit local context | Precision does not imply perfect market data or forecasts |
| Unlimited timing arrays | Memory could grow with uptime | Fixed 4,096-sample windows | Percentiles represent the recent window, not the full session |
| Every HOLD created an audit record | Large idle write volume and storage growth | Persist balances but audit only fills; prune aged deduplication | Actual trade history still grows |
| No coordinator ownership lock | Multiple processes could act on one ledger | OS lock per database | Different databases do not share risk limits |
| Quote deadline included in financial fingerprint | A renewed measurement could prevent reopening a ledger | Separate transient deadline from financial configuration | Changing financial settings still requires another ledger |
| Stored eligibility flag was trusted | Inconsistent profiles could enable paper gates | Recompute policy from raw samples; reject nonfinite clocks | Files are not authenticated attestations of machine origin |
| Missing operator and health controls | Hard to distinguish inactivity, rejection, and outages | PAUSE, FLATTEN, atomic heartbeat, reason codes, and disconnect state | No remote alert delivery or automatic remediation |
| No consistent online backup command | Copying a live database could miss WAL state | SQLite backup API and integrity check | Backup scheduling remains an operator responsibility |
| Single historical evaluation period | Weak evidence about regime stability | Three rolling test months, six candidates per fold, cash alternative | Historical reuse and small research universe remain limitations |

SQLite allows one writer at a time; `BEGIN IMMEDIATE` acquires the write transaction before account decisions. Version 1.1 retains that transactional structure for shared cash/exposure checks and rollback. The coordinator lock serves a different purpose: preventing two strategy loops from owning the same paper database. It does not replace transactional accounting. [1]

The backup command uses SQLite's online backup facility to produce a consistent snapshot, followed by an integrity check and non-overwriting publication. It does not copy only the main file of a live WAL database. The test backs up a ledger while its connection remains open and verifies the restored account state. [2]

## Monetary correctness and stale valuations

Money enters through decimal strings and remains Decimal during accounting. Float64 is reserved for statistical features and model coefficients. Local contexts make calculations independent of surrounding precision settings; tests repeat the same round trip under caller precisions 6, 28, and 50 and verify identical balances without changing the caller's context. Python's context mechanism controls arithmetic precision and rounding; it does not make estimates exact. [3]

A missing fresh valuation is now treated as incomplete portfolio information. The engine retains the last recorded mark for status, freezes global mark-based risk updates while information is incomplete, and blocks new exposure. An available account can still execute its own risk, horizon, or operator-requested paper exit. Health labels last equity as a historical mark, so it must not be interpreted as a presently executable balance.

Timestamp watermarks reject backward event time. Deduplication IDs are retained for at least one day; pruning does not allow an older event to reopen exposure because the account timestamp survives. BUY and SELL records remain in the audit table. Idempotency is local to this paper ledger: no claim is made about exchange order idempotency, fills, or account reconciliation.

The exchange filter adapter checks symbol trading status and loads quantity/notional rules. It still implements only the subset needed by this paper model. Official Binance filters include additional price, quantity, notional, and market-order conditions; passing this adapter is not proof that an actual order would be accepted. [4]

## Timing and feed interpretation

The architecture remains event-driven through Binance public combined WebSocket streams. BookTicker supplies best bid/ask prices, quantities, and update ID, but no source event timestamp E. Consequently, local receipt age cannot distinguish a genuinely fresh quote from an old quote delayed before reception. Closed-candle event timestamps provide an additional lag check, not a complete freshness proof for the order book. Binance documents finite connection lifetime and heartbeat requirements, so reconnection is a normal operational path. [5]

The local REST timing profile retains the prior engineering thresholds: at least 30 successful observations per endpoint, failure rate at most 5%, successful-response p99 at most 1,000 ms, and clock uncertainty at most 250 ms. Decision spacing is at least `max(100, 2 p95)` ms; quote receipt-age tolerance is `min(1000, max(250, 3 p99))` ms. These are configurable-design heuristics expressed in code, not profit-optimized timing or a measured execution service-level agreement.

The loader recalculates counts and deadlines from raw samples rather than trusting precomputed approval. Profiles expire after 24 hours. Clock movement inconsistent with monotonic elapsed time blocks entries for the session. The loop bounds reconnection backoff and keeps writing health during outage waits. A current heartbeat indicates a running coordinator, while quote ages and entry reasons describe market readiness; the two must be interpreted together.

A 30-second public observation received 3,413 messages and experienced two reconnections: one proxy exception and one WebSocket timeout. Recent message-interarrival p95 was 29.13 ms. This is not RTT, order acknowledgment, fill latency, or an improvement relative to the earlier session, which occurred under different market/network conditions. No valid kline-lag or paper-computation measurement was obtained in observation mode. The raw summary is in `stream-development.json`.

## Model design

The base predictor remains Ridge regression using one-minute return, momentum over 5 and 20 bars, 20-bar volatility, relative volume, and candle range. Feature construction is vectorized using rolling array views while preserving causal inputs. Online inference caches features until another closed candle arrives; each quote can still update accounting/risk decisions. This separates feature work from quote-driven risk processing.

The new candidate accounts for changing volatility. For prior 20-bar return volatility sigma and horizon h, define a scale `s = max(sigma, floor) × sqrt(h) × 10000`. The floor is fitted only from training data, with a minimum of 1e-6. Ridge fits log-return labels divided by this scale. Forecasts and the calibrated error buffer are then multiplied by the scale available at prediction time. This is a modeling hypothesis for heterogeneous error magnitude, not an established improvement or a correctly specified volatility process.

Both variants retain regularized least squares, training-only feature normalization, future-label purging at boundaries, and a one-sided 90th-percentile overprediction buffer from later calibration samples. Entry compares a lower forecast bound with round-trip log cost plus a two-basis-point margin. Arithmetic and logarithmic returns are not mixed. Inputs outside the configured training-distance guard are rejected rather than extrapolated automatically.

A nominal 90% lower bound is not a guaranteed 90% probability of profitable trades. Temporal dependence, regime change, calibration sample selection, and the difference between all observations and selected entries affect coverage. Official time-series examples illustrate why shuffled train/test splits can be optimistic and why uncertainty must be evaluated on time-separated observations. Those examples are methodological references, not evidence that this trading strategy is profitable. [6]

## Locked experiment

The protocol was written before the additional test results were inspected and is recorded in `PROTOCOL.json`, whose SHA-256 is included in `evaluation.json`. It fixes BTCUSDT and ETHUSDT, July/August/September 2025 test months, horizons of 1/3/5 minutes, two Ridge variants, alpha 10, error quantile 90%, and a two-log-basis-point entry margin. There are six candidate evaluations per symbol/month, 36 validation candidates in total, without post-test retuning.

Twelve official monthly archives cover April–September 2025, totaling 527,040 one-minute candles. Downloads are checked against published SHA-256 values, normalized, validated for continuity and OHLCV constraints, and atomically published as CSVs. Source URLs, archive hashes, and normalized file hashes are recorded in `datasets/manifest-v1.1.json`. The raw CSVs are regenerated rather than embedded in the Git commit.

Each test month uses the preceding 56 days: 28 fitting, 14 calibration, and 14 selection days. Labels crossing fitting/calibration boundaries are purged; test labels are likewise limited to the test segment. Earlier test months may become training data in later folds, as in a predeclared rolling procedure. This is a historical walk-forward experiment, not genuinely unknown future trading.

Promotion requires positive selection-period PnL, at least 30 closed trades, calibration RMSE below a zero forecast, and a positive lower endpoint of a daily-mean PnL interval. The interval uses a deterministic circular moving-block bootstrap with three-day blocks, 2,000 resamples, and seed 110. With only 14 selection days, its statistical power and tail reliability are limited. It is an additional rejection rule, not a confidence guarantee or a formal multiple-testing correction.

Cash is an explicit deployment choice when no candidate qualifies. A validation-ranked but rejected model is still evaluated for research diagnostics and is clearly labeled as such. The test months report base, fast, slow, stress, momentum-reference, and cash scenarios. Each fold resets virtual capital to 1,000 USDT per symbol, so sums across folds must not be described as a continuous-account equity curve.

Repeated strategy selection can create false positives even when individual backtests appear impressive. The backtest-overfitting literature motivates preserving the trial count, separating selection from evaluation, and resisting parameter changes after observing test results. This release does not implement the paper's combinatorially symmetric cross-validation or claim a measured probability of backtest overfitting. [7]

## Economic results and interpretation

No candidate passed promotion in any of the six symbol/month folds. Validation entry counts were zero. The selected deployment was therefore cash throughout, with zero simulated PnL and zero fees. The validation-ranked research candidates also produced zero trades under the reported latency/cost scenarios. This demonstrates abstention under the gates, not an economic gain or accuracy improvement.

| Test month | BTC momentum-reference net USDT | ETH momentum-reference net USDT | Model deployment |
|---|---:|---:|---|
| July 2025 | −50.0772 | −50.1089 | Cash |
| August 2025 | −50.2062 | −50.1237 | Cash |
| September 2025 | −50.2167 | −49.8737 | Cash |

Reference losses use the same paper risk framework and assumed costs. They are not losses from funded accounts, nor a direct comparison with v0.2 or a commercial bot. Values near five percent reflect risk controls and market moves; an observed loss can cross a configured threshold because exits occur only at the next available observation.

For the validation-ranked one-minute Ridge forecasts, test RMSE was approximately equal to predicting zero. The observed lower-bound coverage ranged from about 85.45% to 94.80% across folds despite nominal 90% calibration. This is direct evidence that the error buffer's coverage varies by period. Diagnostic test scores for all six candidates are retained to expose rather than hide variation; they are not used to revise the selection decisions.

Base assumptions remain 10 bps fees per side, 2 bps slippage per side, and 2 bps spread. Stress uses 15/5/10. Latency scenarios of 50, 250, and 1,000 ms add a previous-volatility impact proxy. One-minute OHLC cannot reconstruct the order book, queue position, partial fills, or intraminute execution path. Thus the experiment cannot determine the most profitable millisecond cadence. Electricity, taxes, funding, and broker-specific commissions are excluded.

## Deployment and verification limits

The suite contains 65 unique automated tests. New cases cover ambient precision independence, stale-symbol isolation, operator controls, old replay rejection after pruning, quote-key mismatches, transient deadline changes, backup consistency, lock exclusion, invalid profiles/clocks, malformed candles, observer startup without model files, scaled-model serialization/causality, and deterministic bootstrap behavior. Existing accounting and historical causality tests remain active. No test count is a certification of profitability.

An Ubuntu bootstrap script installs dependencies and runs tests without enabling a service. An optional systemd unit runs only the public observer. The unit could not be validated against a user manager in this container and has not been tested across an actual host reboot. The operations guide distinguishes installation, supervised paper use, and unattended observation rather than presenting a background process as production trading readiness.

Version 1.1 uses a new database path and rejects the prior schema; it does not transfer old balances or silently erase state. The financial fingerprint remains strict while allowing new transient latency deadlines. Historical model artifacts remain separate from active models. All source, documentation, and messages are English.

Remaining priorities are actual-PC soak testing, current market-data collection with source timestamps/depth, a more informative economically justified signal, genuinely prospective validation, and an execution/reconciliation design before any testnet or funded operation. Futures, forex, stocks, Capital.com execution, and Hapi are still outside this engine. These omissions are material: the 1.1 label identifies the software release, not a completed multi-broker trading product.

## Sources

Sources accessed September 15, 2026. Implementation measurements are reproducible from the named repository artifacts and are distinct from sourced technical facts.

1. SQLite. [Transaction](https://www.sqlite.org/lang_transaction.html). Write transaction and BEGIN IMMEDIATE semantics.
2. SQLite. [Online Backup API](https://www.sqlite.org/backup.html). Consistent snapshot behavior and live-backup constraints.
3. Python Software Foundation. [decimal — Decimal fixed-point and floating-point arithmetic](https://docs.python.org/3/library/decimal.html). Precision contexts and decimal arithmetic.
4. Binance. [Spot API filters](https://github.com/binance/binance-spot-api-docs/blob/master/filters.md). Quantity, notional, and other exchange constraints.
5. Binance. [WebSocket streams](https://raw.githubusercontent.com/binance/binance-spot-api-docs/master/web-socket-streams.md). BookTicker payload, heartbeat, and connection lifetime.
6. Scikit-learn developers. [Lagged features for time series forecasting](https://scikit-learn.org/stable/auto_examples/applications/plot_time_series_lagged_features.html). Temporal evaluation and uncertainty examples.
7. Bailey, Borwein, López de Prado, and Zhu. [The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf), 2015. Selection bias and backtest-overfitting methodology.
8. Binance public data. Archive URLs and SHA-256 values in [the dataset manifest](../../datasets/manifest-v1.1.json). Historical market-data provenance.
