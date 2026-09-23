# Fixed paired holding-period study

```bash
python -u profile_delayed_horizons.py \
  --capture data/delayed-forward-20260922T184115Z/capture \
  --model data/delayed-forward-20260922T184115Z/model.json \
  --output-dir data/delayed-forward-20260922T184115Z/horizon-profile
```

This exploratory diagnostic replays the existing recording once. At decision
time it calculates the frozen five-second model score and applies its unchanged
positive top-bucket cutoff. Entry is the first covered ask 500–750 ms later.
It measures ask-to-bid log returns at 5, 15, 30 and 60 seconds after that entry,
allowing at most 250 ms lateness at each endpoint.

Every horizon uses identical completed entry samples. A boundary, uncovered
quote, receipt gap over one second or missed endpoint discards the entire anchor,
including any shorter labels already observed. Anchors cover nonoverlapping
60-second windows; the next may share the prior endpoint. This reduces sample
count and selects continuous intervals. It is not representative of all signals.
Counts, paired rows and discarded anchors are saved for inspection.

The frozen score is not a forecast calibrated to longer horizons. No fitting,
threshold adjustment or winner selection occurs. All four horizons are reported.
Observed spread is included, but fill size, actual orders, queue position and
additional exit latency are not modeled. A fixed hypothetical fee/slippage
barrier is subtracted only to summarize log-return margins; this is not cash P&L.
Realized returns above that barrier cannot be selected with hindsight.

These results are retrospective, without uncertainty intervals, and do not
establish a new trading strategy. Any proposed longer-horizon rule must be frozen
before evaluation on fresh data. Output paths must be new; existing artifacts
and model files are not modified. No live orders or model approval.
