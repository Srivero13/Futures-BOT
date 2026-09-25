# Fixed BTC-context experiment for ETH

Hypothesis: past BTC returns add predictive information for ETH beyond ETH's own
six candle features. This is a paired feature comparison, not a trading upgrade.
Both earlier short-horizon and hourly trend experiments remain unapproved.

The baseline uses the existing six ETH features. The richer model adds BTC's
1-, 5- and 20-minute log returns and ETH-minus-BTC 20-minute return. No feature
selection, architecture search, GPU training or threshold search is performed.

Both ridge models use alpha 10, expanding training history and training-only
normalization. The preceding month sets the 80th-percentile forecast cutoff and
the nonnegative 90th-percentile forecast-minus-outcome residual buffer. Test
outcomes affect neither weights nor these calibration quantities.

Decisions occur on each UTC hour. Features use only bars closed before that
decision. The target is ETH's reference open one minute after the decision to
its reference open 60 minutes after entry. Labels crossing a training,
calibration or test boundary are excluded. Adjacent return intervals do not
overlap, though serial dependence and overlapping feature histories remain.

Both series require identical minute timestamps; mismatches fail instead of
being silently discarded or filled. A gap in both series resets feature/label
history. Shard identity and checksums are checked before use and after fitting.
Source data must stop before the reserved date. Sample storage is capped at
100,000 hourly examples; raw candles are streamed through a bounded buffer.

```bash
python -u research_cross_asset.py \
  --eth-files data/market-expanded/binance-ETHUSDT-*.csv \
  --btc-files data/market-expanded/binance-BTCUSDT-*.csv \
  --first-test 2026-03-01 --months 6 \
  --reserve-from 2026-09-01 \
  --output data/eth-btc-context-development.json
```

A protocol is saved before building/fitting. Output and protocol paths must be
new. Progress includes aligned minute counts, folds and their results. No
downloads, exchange credentials, orders or updates to frozen models occur.

The report preserves per-fold predictions and labels for paired diagnostics.
Zero, ETH-only and richer model RMSE use exactly the same rows. Cost candidates
require forecast minus residual buffer above the existing reference-price
round-trip cost plus margin: about 28 log-bps, including 10 bps fees per side,
2 bps slippage per side, 2 bps full spread and 2 bps margin. The residual buffer
is a heuristic, not guaranteed statistical coverage. There is no OOD filter.

This reports no execution P&L. Historical candle availability at the decision
time is assumed; real delayed data delivery, fills and sizing are not modeled.
Selected means and correlations do not establish profitability. March–August
has already been inspected, so this remains retrospective development even
though the feature hypothesis differs. September stays excluded. Any promising
result needs frozen forward evaluation and an execution test before advancement.
