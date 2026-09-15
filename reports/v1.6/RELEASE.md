# Version 1.6: startup, training reliability, and nonlinear research

## Delivered

The release adds a 27-term degree-two Ridge model, a standard-library startup doctor, a guarded observer/paper launcher, training preflight checks, bounded-memory progress reporting, run locks, atomic model publication, content-identified run directories, completed-fit resumption, and model/report integrity checks. It pins base dependencies to NumPy 2.3.5 and websocket-client 1.8.0. Public installation and troubleshooting instructions are in [Start here](../../docs/START_HERE.md).

This is a research and paper release. It does not promise zero crashes, improve every subsystem, certify 24/7 stability, or demonstrate profitable execution. Active model artifacts remain unchanged and no new model is approved automatically.

## Audit findings and fixes

| Finding | Change | Validation |
|---|---|---|
| Missing WebSocket dependency stopped startup in a fresh environment | Doctor checks pinned dependency versions; launcher provides an actionable exit | Injected missing dependency and fresh-venv installation |
| Model files could be partially written on failure | All model saves use atomic JSON replacement | Injected replacement failure preserves the original artifact |
| Repeated training could overwrite named outputs or duplicate work | Input/configuration/software hashes identify each run; per-run process lock | Different parameters create separate runs; concurrent mutation is rejected |
| Failed evaluation required repeating a completed fit | Fit/calibration checkpoint plus verified resumption | Injected evaluation failure resumes without invoking fitting |
| Bad coverage or low output space was detected late | Full data validation and sample-count checks before fitting; periodic disk reserve check | Invalid dates, missing files, changed inputs, low disk, and insufficient segments |
| Completion could be mistaken for partial output | Final completion marker authenticates model/report hashes | Corruption rejected; interrupted work has no completion marker |
| A final health-write failure could skip ledger cleanup | Close the ledger in a nested finally block | Injected shutdown write failure still closes the ledger |
| Transient initial exchange metadata failure ended paper startup immediately | Three bounded read-only retries within the startup duration budget | Success after transient error and bounded permanent failure |

The doctor does not query exchanges or validate hardware/clock stability. The launcher exits with a diagnostic when it cannot safely start; it does not blindly restart financial state. The existing stale-feed, cost, loss, exposure, pause, horizon, and replay protections remain in place. Socket-close errors are recorded instead of overriding normal cleanup.

## Model design

The nonlinear model retains the six causal one-minute features and adds six squares plus fifteen pairwise interactions. Fit-only scaling and Ridge regularization control the enlarged design matrix; streaming augmented QR and a final small least-squares solve avoid normal-equation inversion. The fit, calibration, and holdout remain chronologically separate, with cross-boundary labels purged and gaps resetting feature windows. Model schema/checksum validation supports both linear and polynomial artifacts. Non-finite and out-of-distribution predictions fail closed.

Degree-two expansion can represent interactions that a linear model cannot; a synthetic interaction test demonstrates that capacity. It is not proof of market predictability. Polynomial terms add flexibility and can overfit; see the [polynomial feature reference](https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.PolynomialFeatures.html). This implementation uses NumPy directly and adds no scikit-learn dependency.

The new trainer supports fixed horizons of 1, 3, or 5 minutes, a positive Ridge penalty, and chunks of 32–65,536 examples. Defaults are a three-minute horizon, alpha 10, and 4,096 examples per chunk. It sets BLAS thread-count defaults to one before importing NumPy when invoked as the CLI; explicitly configured environment values are preserved. Calling it after another library has initialized BLAS does not reconfigure that library.

## Historical comparison

The [protocol](PROTOCOL.json) fixed both candidates before the comparison. Data consists of 527,040 existing Binance BTCUSDT/ETHUSDT candles from April–September 2025, totaling 44,108,369 canonical CSV bytes, checked against the previously published archive-derived manifest. These periods were already used in earlier releases; this is retrospective validation, not newly unseen evidence. No fresh source acquisition or 30+ GB training was performed.

Each candidate fitted 230,376 examples before September 8, calibrated on September 8–14, and evaluated September 15–30. Both candidates are reported; neither is selected or promoted using the holdout. Since nonlinear OOD rejection removes additional examples, the table uses only the intersection accepted by both models:

| Symbol | Common accepted rows | Linear RMSE, log bps | Polynomial RMSE, log bps | Zero-return RMSE, log bps |
|---|---:|---:|---:|---:|
| BTCUSDT | 22,979 | 6.008386 | 6.009405 | 6.007273 |
| ETHUSDT | 22,925 | 11.534910 | 11.533512 | 11.533087 |

The polynomial model was slightly better than linear on ETH and slightly worse on BTC. Both remained worse than zero-return forecasts on the common samples. Every candidate produced zero cost-gate candidates under the existing assumed 26 bps round-trip cost plus 2 log-bps margin. No statistical significance or trading edge is claimed. P&L remains null because this run evaluates forecasts, not execution or fills.

Per-model evaluation and checksummed artifacts are included beside this report. Use `compare_v16.py` to reproduce the common-row comparison with the saved models and original CSVs. The v1.5 approximately 730× batch benchmark applies to the optimized linear batch path, not the new polynomial model or total bot runtime. This release makes no new speed multiplier claim.

## Reliability evidence and limits

- All 104 tests passed with optional Numba installed. In a fresh base virtual environment, 103 passed and the one optional Numba test was skipped. This includes 22 added tests covering nonlinear capacity, schema/shape handling, causal invariance, locks, interrupted/reused runs, disk failures, corrupted artifacts, launcher errors, common-row comparison, and shutdown cleanup.
- A fresh virtual environment installed the pinned base requirements and passed the doctor. OS installation, systemd host startup, Windows/macOS, and deployment-specific hardware were not exercised.
- A five-second observer probe recorded one WebSocketProxyException, no market messages, and returned normally after approximately five seconds. This demonstrates bounded handling of that failure, not successful market connectivity.
- Completed fit/calibration checkpoints survive evaluation failure. Interruptions during fitting restart the fitting passes; there is no partial QR checkpoint. A hard kill can leave a stale status until the command is rerun. File replacement is atomic at the application level; hardware/filesystem durability across power loss is not certified.
- Raw data remains on disk, and chunking bounds working data; no 30+ GB memory or throughput benchmark was run. Initial hashing, validation, and repeated file passes consume I/O. Independent simultaneous runs still compete for RAM/CPU/disk.

Evidence: [test summary](validation.json), [fresh-environment doctor](doctor-clean.json), [observer probe](observer-probe.json), and the per-symbol comparison JSON files. No real orders were sent.
