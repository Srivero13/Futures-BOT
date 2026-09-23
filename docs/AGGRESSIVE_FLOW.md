# Receipt-ordered aggressive-flow experiment

```bash
python -u research_aggressive_flow.py \
  --training-capture data/live-refresh-20260920T220644Z \
  --evaluation-capture data/delayed-forward-20260922T184115Z/capture \
  --output-dir data/aggressive-flow-development
```

This compares the three-feature baseline against four added features on identical
rows: taker notional imbalance over one and five seconds, log(1 + aggregate trade
events per second) over five seconds, and five-second flow imbalance multiplied
by best-level quantity imbalance. The aggregate event rate is not an underlying
individual trade count. No rejected quote-dynamics features are added.

For recorded Binance aggTrade messages, buyer-maker `m=true` contributes seller-
initiated notional; `m=false` contributes buyer-initiated notional. Imbalance is
(buy notional - sell notional) / total notional, with zero for an empty window.
Windows exclude their lower time boundary. Only trade records preceding the
quote record are used, even when monotonic receipt timestamps tie. Exchange event
timestamps are not used to insert trades before they were received.

A bounded secondary reader follows the same manifest order and verifies every
part hash and size independently. Replay verifies the book and raw recording.
Trade-ID gaps or duplicates, quote gaps, session/coverage/snapshot boundaries and
clock flags clear flow history and restart sampling. Missing activity is not
backfilled; five seconds of history plus inherited one-second warm-up are needed.
An empty observed window does not prove no market trading occurred.

Labels retain the delayed ask-to-bid protocol. Both ridge models use alpha 10,
training-only scaling and training-only top-bucket cutoffs on identical rows.
Reports are retrospective development analysis, not new forward validation.
Returns exclude fees, additional slippage and fill-size checks. No GPU, new
recording, live orders, hyperparameter search or model approval is involved.

Expect two replay passes (one per recording), with a secondary sequential read
for flow. Memory use is bounded; a 100,000-event five-second window cap fails
explicitly rather than silently truncating history. Outputs must use a new folder.
