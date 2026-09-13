# v0.2 validation

- 21 automated tests passed with Python 3.12 on Linux.
- Tests cover cost accounting, hourly/PnL reconciliation, execution after signals, invariance of the past under future changes, duplicate/gapped candle rejection, gaps exceeding stops, minimum sizes, isolation, restarts, sample persistence, and live-mode blocking.
- Two processes ran for 70 iterations and restarted for 10 more: 80 events per ledger and 20 recovered samples. One additional iteration verified metadata and the corrected report.
- Capital.com queries were tested only with simulated responses. No private account was connected.
- Six monthly Binance archives were downloaded; their SHA-256 checksums match the published checksums.
- 51,840 OHLCV candles are included; three training candidates per symbol and 22 validation/holdout evaluations, totaling 28 simulations.
- Full results and curves are included. Parameters were not reoptimized after viewing the final evaluation.
- Paper reporting rejects inconsistent initial capital and suppresses temporal rates for synthetic data and sessions shorter than one hour.
- No orders were sent. Windows and the user's hardware were not tested. There is no evidence of future profitability.
