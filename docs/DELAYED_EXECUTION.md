# Delayed-model execution feasibility

Replay the existing forward capture once through two independent diagnostics:

```bash
python -u diagnose_delayed_execution.py \
  --capture data/delayed-forward-20260922T184115Z/capture \
  --model data/delayed-forward-20260922T184115Z/model.json \
  --output-dir data/delayed-forward-20260922T184115Z/execution
```

The top-bucket engine retains the positive forecast and frozen training cutoff.
The cost-gated engine additionally requires the forecast to reach the deterministic
break-even barrier for the assumed fees and slippage. It does not lower costs,
refit the model, or tune thresholds to this recording. Neither sends orders.

For per-side fee `f=0.001` and adverse slippage `s=0.0002`, the barrier in log-bps is
`10000 * log((1+s)*(1+f)/((1-s)*(1-f)))`, approximately 24.000007.
The target already uses entry ask and exit bid, so spread is not added again.
This identity assumes sufficient fills at those quotes and constant proportional
costs. Comparing a mean log-return forecast to it does not guarantee positive
expected cash P&L or provide a confidence bound.

Entries use 100 quote units, a 500 ms delay and a five-second holding period after
entry. Both entry and exit permit 250 ms scheduling lateness. Top-level size is
checked, but queue fills, exchange filters and quantity rounding are not modeled.
There is no additional exit latency. These are scenarios, not measured order RTT.

`top_bucket.json` and `cost_gated.json` contain individual closed simulated trades,
compatible with `attribute_micro_costs.py`. `summary.json` contains both summaries.
Schedules diverge after trades; engine differences are not a paired causal estimate.
Unresolved positions are counted, excluded from closed totals, and never silently
assigned zero P&L. These engines may resume diagnostics afterward, so neither is
a complete portfolio simulation. Zero trades would show abstention under these
assumptions, not model success or proof that every trading approach is unviable.

This is retrospective development analysis. The model remains unapproved.
