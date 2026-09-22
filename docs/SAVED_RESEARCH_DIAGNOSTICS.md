# Saved research diagnostics

Use `diagnose_saved_research.py` to inspect saved paired forecast reports without
training or requiring PyTorch. It reads bucket means/counts and RMSE, checks
count consistency and finite moments, and fingerprints each result file.
Per-report protocol files are skipped. Existing output files are protected.

```bash
python diagnose_saved_research.py \
  --reports data/parallel-20260918T145152Z/*.json \
  --output data/parallel-saved-diagnostic.json
```

The report contains weighted mean forecast and actual return, mean error,
squared mean error as a fraction of MSE, centered error RMSE, and full bucket
statistics. Mean squared error equals squared mean error plus error variance.
Removing the test mean error is only an algebraic diagnostic: it does not provide
a bias correction available before the test. Empty buckets stay undefined.

Pooled RMSE weights each fold's squared error by its number of rows, then takes
the square root. It is not an arithmetic mean of monthly RMSE values. Compare
only reports from the same experiment schedule; the reader does not establish
independence, market comparability, or statistical significance.

Aggregate reports cannot identify daily error spikes, tail losses, or individual
bad predictions. Those require row-level predictions from another evaluation.
Bucket return means are before transaction costs and are not realized trading
returns. This command selects no strategy, retrains nothing and approves no model.
