# Paired trade-flow research

`evaluate_tradeflow.py` tests a fixed addition to the candle-only ridge model.
It requires three complete months of passing alignment audits, including their
unchanged raw archives, summaries, candle shards and manifests on the same PC.
Audit input paths are absolute. Copying reports alone is insufficient.

The first month trains both models on a non-overlapping 15-minute UTC grid.
The second month determines forecast bucket cuts; the third evaluates them.
Labels crossing split boundaries are excluded. Scaling uses training data only.
Ridge alpha is fixed at 10; there is no parameter search or OOD filtering.
Both models use exactly the same rows and next-open 15-minute return labels.

The added features are trailing 5- and 20-minute signed quote-notional imbalance
and trailing 5-minute aggregate-event activity relative to the 20-minute average.
Each feature is keyed by the close of its latest minute, never its opening time.
Gaps reset the rolling window. These are trade-flow features, not order-book depth.

```bash
python evaluate_tradeflow.py \
  --audits data/eth-tradeflow-2026-06-alignment.json \
           data/eth-tradeflow-2026-07-alignment.json \
           data/eth-tradeflow-2026-08-alignment.json \
  --symbol ETHUSDT --start 2026-06-01 --reserve-from 2026-09-01 \
  --output data/eth-flow-paired-development.json
```

Progress is printed at verification, feature construction and each model fit.
A protocol is saved before fitting; an existing result is never overwritten.
Source hashes are checked before and after evaluation. Memory is bounded by the
three-month input restriction; no raw event archive is expanded in memory.

Compare both models against the zero-return RMSE and compare their Spearman
correlations and bucket returns. A negative flow-minus-candle RMSE means lower
forecast error with flow, not positive trading P&L. This single development split
has no significance claim, execution simulation, fees, live receipt latency or
model approval. No deployable model is exported. Do not tune on this result and
then describe the same period as untouched validation.

## Fixed rolling development batch

Run `research_tradeflow_batch.py --output-dir data/eth-flow-rolling-run1` to
acquire March–August 2026 ETH spot flow and evaluate May, June, July and August.
Each test month uses the preceding month for calibration and the month before
that for training. All folds use the same features, horizon and ridge penalty.
August is already inspected development data, not a newly untouched holdout.

The batch reuses checksum-verified downloads in `data/tradeflow-pilot`, audits
all six months, then saves individual paired reports and `summary.json` in the
new output directory. It fails on missing candle shards, a failed download or
a failed audit. The download directory retains its 8 GiB budget. Downloads have
bounded retries. Runtime depends on the network; the job stops when finished.

Use a new output directory after an interrupted batch. Completed archives remain
reusable; audits and evaluations are rerun. No live trading or automatic parameter
search occurs. For terminal persistence, run inside tmux and disable automatic
suspend in Ubuntu power settings.
