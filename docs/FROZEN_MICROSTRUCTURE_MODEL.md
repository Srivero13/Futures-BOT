# Frozen microstructure CPU model

Train one fixed ridge model (alpha 10) on a completed development dataset:

```bash
python train_microstructure.py fit --dataset data/microstructure-20260920 \
  --output data/microstructure-model-v1.json
```

The features are spread, best-level quantity imbalance, and log total best-level
quantity. All normalization and forecast bucket cuts use development samples.
This small dataset does not require a GPU. The model format is separate from the
live engine's models and always remains unapproved.

Collect a new recording after fitting, build it with the unchanged sampler, then:

```bash
python train_microstructure.py evaluate --dataset data/microstructure-forward \
  --model data/microstructure-model-v1.json \
  --output data/microstructure-forward-evaluation.json
```

The evaluator rejects the same capture, identical samples, earlier or overlapping
wall-clock intervals, samples predating model freezing, mismatched sampling code
or settings, and changed sample hashes. Model and output files are not overwritten.
The runner hash must match the one used for fitting. Dates use local wall-clock
metadata; these checks are not proof that nobody inspected the evaluation data.
Freeze before collection, and do not tune parameters from prospective results.

Metrics include forecast and zero-return RMSE, forecast and raw-imbalance rank
correlation, mean error and training-defined forecast buckets. Evaluation does
not refit weights, normalize on new data or choose thresholds. Labels are five-
second midpoint changes, not executable returns. There is no commission, fill,
queue-position or latency model. No result automatically approves real trading.
A single later recording still provides limited evidence across market conditions.
