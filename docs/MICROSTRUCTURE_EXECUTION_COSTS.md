# Frozen-model execution-cost diagnostic

`diagnose_execution_microstructure.py` replays a later recording against the frozen
model. It makes causal long-only decisions from covered quotes after a one-second
warm-up, no more often than every five seconds, with at most one pending entry or
position. Selection requires a positive forecast in the highest training-defined
bucket. There is no fitted threshold, retraining, or automatic strategy approval.

An entry waits 500 ms and uses the first subsequent quote, rejecting lateness over
250 ms. It buys at the ask plus 2 bps adverse slippage. The exit uses the first
quote at least five seconds after entry, again allowing 250 ms lateness, selling
at bid minus 2 bps. No additional exit-order delay is modeled. Both sides pay a
fixed assumed 10 bps fee on their actual notionals. These assumptions are not a
lookup of a user's account fees. Nominal position size is 100 quote units.

Reported midpoint P&L minus spread/slippage cost minus fees equals net P&L for
completed simulated trades. Displayed top-level quantity must cover the modeled
quantity. This is not an exchange fill guarantee, and quantity/price filters,
rounding, queue position and market impact are not modeled.

A refresh, gap, uncovered quote, clock-jump flag or disconnect cancels pending
entries and marks open positions unresolved. Unresolved trades are counted and
excluded from closed-trade totals. They are NOT assumed to close at zero loss.
The report therefore never claims a complete portfolio execution result, even
when no unresolved positions occur. Receipt time is not matching-engine time.

```bash
python diagnose_execution_microstructure.py \
  --capture data/forward-20260921T150926Z/capture \
  --model data/forward-20260921T150926Z/model.json \
  --output-dir data/forward-20260921T150926Z/execution-costs
```

This is a retrospective diagnostic on the already examined forward recording.
Keep the model and assumptions fixed when interpreting results. A five-second
hold after delayed entry differs from the original five-second prediction target.
Use the findings to assess economic feasibility, not as evidence of live profits.
The output directory must be new; inputs and existing reports remain unchanged.
