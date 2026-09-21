# Continuous microstructure samples

`build_microstructure.py` re-verifies raw recording hashes and replays the book
while producing a bounded research dataset. A callback from replay supplies only
linked depth quotes. Connection changes, snapshots, snapshot refreshes, uncovered
quotes, detected sequence gaps and recorded clock jumps invalidate pending labels.
A depth receipt gap greater than one second also resets sampling.

After a one-second warm-up, a sample stores the current spread, best-level base
quantity imbalance and log of total best-level quantity. Its target is midpoint
log return in basis points at the first covered update at least five seconds
later. If that update is more than 250 ms late, the sample is discarded. A new
sample starts at the completed/discarded label endpoint, so labels do not overlap.
The fixed horizon and timing tolerances are engineering research choices, not
optimized trading timings. Receipt timestamps include application buffering.

```bash
python build_microstructure.py \
  --capture data/live-refresh-20260920T220644Z \
  --output-dir data/microstructure-20260920
```

The output directory must be new. The builder saves `samples.jsonl`, a fresh
`replay-verification.json`, and `summary.json` containing hashes and settings.
Only a completed summary marks the dataset as ready. Failed verification prevents
publication of the samples. The 20,000-sample cap bounds memory. Raw recordings
are never modified. Old replay reports do not substitute for re-verification.

The summary reports sample counts, discarded pending labels, zero-return RMSE and
descriptive imbalance/target Spearman correlation. This is not a train/test result
or significance test. Do not select parameters from this correlation and describe
that same recording as an untouched holdout. No neural training, costs, simulated
fills, model export or trading approval occurs. Different recordings remain
separate datasets, and receipt monotonic timestamps are local to each process.
