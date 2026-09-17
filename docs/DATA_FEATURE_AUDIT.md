# Development data and feature audit

`audit_v16.py` checks the development corpus before another model experiment.
It uses the base requirements, needs no GPU or API keys, and never edits candles,
models, trading settings, or approvals.

```bash
python audit_v16.py \
  --files data/market-expanded/binance-ETHUSDT-*.csv \
  --symbol ETHUSDT \
  --start 2026-03-01 \
  --end 2026-09-01 \
  --reserve-from 2026-09-01 \
  --horizons 15 60 \
  --output data/eth-development-audit.json
```

Start/end must be UTC month boundaries; end is exclusive and cannot exceed the
reserved date. Supply chronological verified Binance CSV shards and JSON sidecars.
Every sidecar must include `last_open_ms` before the reservation and matching
symbol, venue, timeframe and SHA-256. Do not include September shards in this
example. Preceding history is allowed for warm-up. Existing reports are protected.

The shared reader rejects unordered/duplicate timestamps, misalignment, nonfinite
or nonpositive prices, negative volume and inconsistent OHLC bounds. On invalid
input the audit stops without publishing a complete report. Fix the source problem
rather than removing rows just to make the audit succeed.

Monthly quality results count observed and missing minutes, including missing
month boundaries. Inspection flags are fixed before the run:

- Zero-volume candles.
- Absolute close-to-close log moves exceeding 100 basis points in one minute.
- Absolute open-to-previous-close log jumps exceeding 100 basis points.
- Volume exceeding 20 times the mean of the preceding 20 contiguous candles.

Price comparisons require adjacent minutes; volume history resets on gaps. A
zero previous-volume mean produces no ratio flag. Up to 30 initial flagged events
are saved alongside full counts and maxima. Flags can represent genuine market
activity. They are not evidence that data should be deleted. Passing provenance
checks proves agreement with local sidecars, not independent exchange authenticity.

For each horizon, features and subsequent returns are sampled on a fixed UTC
grid with non-overlapping label intervals. Feature windows reset on gaps. The
six existing causal features are audited without model OOD rejection, so counts
may differ from model-accepted research. Monthly Pearson and tie-aware Spearman
correlations, feature ranges, means and standard deviations are reported.
Constant variables have null correlation. Monthly labels group by decision time
and can cross internal month boundaries, but labels ending at or beyond the
overall end are excluded. Empty months have no feature report; quality results
still include their missing-minute counts.

The summary counts positive/negative correlation months and gives equal-weight
means over defined months. There are no p-values, feature rankings selected for
trading, or automated model changes. Univariate association does not establish
incremental feature contribution, causation, profitability or statistical
significance. Inspect the output before defining a separate new hypothesis.

Memory is bounded to a single month's feature/return pairs with a 100,000-row
cap; quality scanning retains only a small rolling window and limited examples.
Input checksums are rechecked before publishing. No reserved-period outcomes are
reported. This date guard cannot prove data was unexamined through other tools.
