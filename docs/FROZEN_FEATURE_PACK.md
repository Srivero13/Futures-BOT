# Frozen three-model comparison

Freeze once using only the saved original training datasets:

```bash
python frozen_feature_pack.py freeze \
  --dynamics-training data/quote-dynamics-development/training \
  --flow-training data/aggressive-flow-development/training \
  --output data/frozen-feature-pack.json
```

The pack contains the baseline, quote-dynamics extension and aggressive-flow
extension. All use ridge alpha 10, training-only scaling and fixed training
80th-percentile cutoffs. Sample matching requires identical decision, entry and
exit timestamps and identical baseline features and labels. At least 100 common
samples are required. Source counts and paired counts are reported.

Record fresh data only after freezing. Evaluate with:

```bash
python -u frozen_feature_pack.py evaluate \
  --capture YOUR_NEW_CAPTURE \
  --pack data/frozen-feature-pack.json \
  --output-dir YOUR_NEW_EVALUATION_DIRECTORY
```

Evaluation builds both feature sets, uses their exact timing intersection, and
never refits weights, scaling or cutoffs. It rejects captures starting before
freeze, code changes, symbol changes and reused development recordings. Both
builders verify raw-file integrity. The pack and output paths cannot be overwritten.
Keep this same pack and code for subsequent independent captures across days.
Do not tune on interim results or automatically select the best model.

Metrics include RMSE, zero-return baseline, Spearman, selected-sample mean return
and cost-eligible forecast counts. Quote returns include spread but not fees,
extra slippage or fills. Cost eligibility is not a trade or profit guarantee.
All models remain unapproved; no live orders are sent. Local timestamps and
hashes enforce reproducibility and chronology, not proof of economic validity.
