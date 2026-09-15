# Futures-BOT 1.5 release report

## Outcome

Version 1.5 delivers a faster inference path and a bounded-memory training workflow. It does not establish a profitable strategy, a 200× total-bot speedup, successful new multi-source acquisition, or a completed 30+ GB training run. New research models remain unapproved and do not replace active model artifacts.

## Engineering measurements

Five warmed trials, 100,000 distinct synthetic float64 feature vectors, identical v1.1 model and rejection rules, Python 3.12.14 / NumPy 2.3.5 on the development x86_64 runtime:

| Workload | v1.1 median | v1.5 median | Ratio |
|---|---:|---:|---:|
| Scalar-loop predictions vs compiled batch | 670.087 ms | 0.918 ms | 729.75× |
| Scalar-loop predictions vs NumPy batch | 686.745 ms | 9.773 ms | 70.27× |
| Same-candle quote decisions vs cached forecasts | 724.295 ms | 43.731 ms | 16.56× |

The 200× target was exceeded only for warmed compiled batch throughput relative to the previous scalar API loop. This is mostly removal of Python/per-row array overhead. It is not a comparison against another optimized batch implementation. The NumPy comparison shows substantial speedup without compilation; differences between separate trials include ordinary runtime variation. Maximum prediction difference was 2.22e-16 bps in this workload. The first compiled batch call took 247.84 ms, including available cache loading/compilation. Cached-quote measurements exclude the initial once-per-candle forecast and still recompute cost gates for varying costs.

These microbenchmarks exclude CSV reading, features, training, Decimal ledger operations, the scheduler, network, and order execution. The quote decision workload produces ordinary decision dictionaries in both versions. The distinct-vector batch workload performs predictions only in both versions. No timing settings were loosened. Performance on other deployment hardware and network conditions was not measured. Numba uses `fastmath=False`; IEEE behavior is not relaxed to increase the score. See [Numba performance guidance](https://numba.readthedocs.io/en/stable/user/performance-tips.html).

Raw samples: [compiled benchmark](benchmark.json), [NumPy benchmark](benchmark-numpy.json). Reproduce with `python benchmark_v15.py --compiled --output data/benchmark-v15-local.json`.

## Training and data

The [protocol](PROTOCOL.json) was fixed before evaluation. Initial new-data requests to Binance archives and Coinbase candles timed out, so the requested October multi-source experiment was not run. Instead, this release performed a retrospective reanalysis of existing, checksum-verified Binance BTCUSDT and ETHUSDT one-minute candles from April through September 2025. These periods had already been examined in v1.1 and are not newly unseen market evidence.

There were 527,040 raw candles, totaling 44,108,369 canonical CSV bytes. Each model fitted 230,376 examples before September 8, calibrated on 3,359 non-overlapping labels from September 8–14, and evaluated 23,037 examples from September 15–30 after boundary purging. One larger expanding fitting window replaces the earlier short rolling fit in this fixed experiment; its outcome should not be presented as an apples-to-apples strategy improvement over v1.1's different selection procedure.

| Metric | BTCUSDT | ETHUSDT |
|---|---:|---:|
| Training + evaluation seconds | 5.421 | 5.388 |
| Peak process RSS, MiB | 36.14 | 36.25 |
| Accepted holdout examples | 23,028 | 22,987 |
| OOD rejections | 9 | 50 |
| Forecast RMSE, log bps | 6.06453 | 11.54690 |
| Zero-return RMSE on identical accepted rows | 6.06415 | 11.54635 |
| Lower-bound empirical coverage | 88.41% | 88.52% |
| Candidates above assumed cost gate | 0 | 0 |

Both models were slightly worse than zero-return predictions on RMSE. Coverage fell below the calibration target of 90%. No cost-gate candidates occurred under an assumed 26 bps arithmetic round-trip cost plus a 2 log-bps margin. These are model-screening results, not P&L or evidence that losses are impossible. P&L is explicitly null because no execution backtest was performed for v1.5. The new pipeline does not model futures funding, liquidation, queue position, partial fills, or microsecond market structure. More historical candles did not produce a demonstrated edge.

Training uses train-only streaming moments, augmented QR reduction, and a final small SVD solve; no inverse of X'X is formed. Calibration and holdout remain chronologically separate with target boundary purging. Gaps reset causal windows. A maximum 100,000-error reservoir bounds calibration memory; above that size its quantile is approximate. This run retained every calibration error. Fit/calibration/evaluation each scan files without materializing the full corpus; provenance hashes are verified before and after the run.

## Multi-source and large-data capability

The new downloader supports Binance monthly ZIP archives with official checksum validation and Coinbase paginated candles. It records venue, symbol, requested coverage, missing minutes, file hashes, and retrieval time, and resumes verified shards. Source fixtures verify normalization, microsecond Binance timestamps, Coinbase pagination/range filtering, and restart behavior. Live acquisition remains unverified in this release because of endpoint timeouts. Each venue/symbol is trained separately; there is no assumption that USDT equals USD or that correlated venues are independent samples.

Bounded chunks enable processing beyond RAM capacity, but 30+ GB was not downloaded or trained here. The workspace had only about 30 GB free at the start. The measured low RSS applies to the 44.1 MB corpus and is not a 30 GB benchmark. See the [installation, acquisition, and training guide](../../docs/V1.5.md) for running larger real datasets on a research host. Avoid padding, duplicate candles, or adding low-quality sources merely to reach a byte count.

## Validation and scope

All 82 automated tests passed, including 17 new tests covering feature/label chunk equivalence, shard overlap rejection, gap handling, future leakage, QR/SVD numerical agreement, optional compiled inference, OOD rejection, current-cost rechecks, source identity, page boundaries, timestamp units, checksum resume, and bounded sampling/output sizes. Existing Decimal accounting, risk, stale-feed handling, and operator-control tests remain passing.

Live forecast caching is invalidated on closed candles, connection resets, and clock resets. Existing freshness, pause, exposure, loss, and exit controls still run at their prior cadence. The release retains the existing paper configuration and database paths for continuity; health reports identify version 1.5.0. No broker credentials were used and no real orders were placed.
