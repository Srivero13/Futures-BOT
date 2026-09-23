# Paired best-quote dynamics research

Run one retrospective experiment using existing recordings:

```bash
python -u research_quote_dynamics.py \
  --training-capture data/live-refresh-20260920T220644Z \
  --evaluation-capture data/delayed-forward-20260922T184115Z/capture \
  --output-dir data/quote-dynamics-development
```

The builder adds five causal features: one-second midpoint log return, one-second
imbalance change, one-second log best-level quantity change, one-second spread
change, and five-second midpoint log return. Lag values use the last quote at or
before the lag time. Actual lag lengths are saved. A bounded five-second history
is maintained; receipt gaps over one second and replay boundaries clear it.
These are best-quote dynamics, not full depth or aggressive trade flow.

The original delayed-label rules are reused: entry ask 500–750 ms after decision,
exit bid 5–5.25 seconds after entry, and nonoverlapping labels. Features are stored
at decision time and cannot be updated with entry or exit information. Five
seconds of history precedes the inherited one-second warm-up. This changes sample
availability, so both models are refitted on exactly the same training rows and
evaluated on exactly the same later rows.

The three-feature baseline and eight-feature extension use ridge alpha 10 with
training-only scaling and training-only 80th-percentile cutoffs. Both also require
a positive forecast when reporting selected means. No hyperparameter search or
GPU is used. Model weights are saved only for reproducibility, not live loading.

All raw inputs are replay-verified; sample hashes and builder provenance are
retained. Reports include RMSE, zero-return RMSE, ranking correlation, selected
sample counts and mean quote returns. Negative `dynamic_minus_base_rmse_log_bps`
favors the extension. This is retrospective development on already inspected
recordings. It has no uncertainty intervals, P&L simulation or approval. Returns
include spread but exclude fees, extra slippage and fill/size checks. Any proposed
strategy must still be frozen before a new forward test.

Output directories must be new. Existing models and recordings remain intact.
