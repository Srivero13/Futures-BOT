# Delayed-entry microstructure research

This separate experimental pipeline matches the execution diagnostic timing:
features at decision time; first covered ask 500–750 ms later; first covered bid
5–5.25 seconds after that entry. The label is `10000 * log(exit_bid / entry_ask)`.
It includes the observed spread, but excludes fees, additional slippage, order
size, queue position, and fill guarantees. It is not portfolio P&L.

Receipt gaps over one second and replay boundaries discard pending labels.
Warm-up is one second. Samples do not overlap. Entry and exit quotes are labels,
never input features. All three features, ridge alpha 10, and training bucket
cuts remain fixed; the protocol is not selected using evaluation scores.

Build and fit on an existing development capture:

```bash
python -u build_delayed_microstructure.py \
  --capture data/live-refresh-20260920T220644Z \
  --output-dir data/delayed-development-20260920
python train_delayed_microstructure.py fit \
  --dataset data/delayed-development-20260920 \
  --output data/delayed-model.json
```

Output paths must be new. Keep the frozen model unchanged. Record a new capture
with `record_market.py` after fitting. Build that capture with the same builder
into a separate directory, then run:

```bash
python train_delayed_microstructure.py evaluate \
  --dataset data/delayed-forward-dataset \
  --model data/delayed-model.json \
  --output data/delayed-forward-evaluation.json
```

Evaluation requires a separate recording taken after model freezing, matching
builder hashes, verified datasets and nonoverlapping labels. Existing recordings
cannot qualify as a new forward test. The prior midpoint pipeline remains intact;
its model type and execution loader deliberately reject this different model.
The delayed model has no live loader. All outputs remain unapproved research.
Discarded intervals and unresolved execution positions remain selection risks;
forecast diagnostics do not resolve those positions or establish profitability.
