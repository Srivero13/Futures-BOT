# Saved delayed-model uncertainty diagnostic

Run on the original development dataset and the already evaluated forward data:

```bash
python diagnose_delayed_uncertainty.py \
  --training data/delayed-development-20260920 \
  --dataset data/delayed-forward-20260922T184115Z/dataset \
  --model data/delayed-forward-20260922T184115Z/model.json \
  --output data/delayed-forward-20260922T184115Z/uncertainty.json
```

No new recording or modification to the frozen model is required. The tool checks
model and dataset provenance through the existing evaluation gates. It fits an
imbalance-only ridge baseline (alpha 10) on the original training rows only.
This baseline was introduced retrospectively, not frozen before the recording.

Two thousand paired cluster-bootstrap replicates use fixed five-minute occupied
wall-time blocks and seed 1729. Every draw retains identical rows for both models.
Negative model-minus-baseline RMSE favors the frozen model. The top-bucket mean
uses the frozen training cutoff and includes observed spread, but excludes fees,
additional slippage, depth checks and unresolved execution positions.

The 95% percentile intervals are conditional diagnostics for this recording,
not guaranteed confidence coverage or trading approval. They omit training
uncertainty; dependence beyond five minutes and changing market conditions can
invalidate their interpretation. Empty intervals are not imputed; unequal block
sizes are retained. A bucket interval is null if fewer than 1,900 replicates
contain selected samples. No strategy parameters are selected by these results.
