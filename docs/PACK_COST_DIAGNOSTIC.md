# Frozen feature pack cost diagnostic

Supply the applicable taker fee and a separately justified slippage assumption.
For example, 0.100% per side is 10 basis points. A displayed BNB discount is
conditional; do not assume it applies without satisfying its conditions.
The tool does not verify account fees or contact the exchange.

```bash
python diagnose_pack_costs.py \
  --pack data/frozen-feature-pack.json \
  --reports data/feature-forward-*/evaluation/report.json \
  --fee-bps-per-side 10 \
  --slippage-bps-per-side 2 \
  --output data/feature-pack-cost-diagnostic.json
```

Inputs undergo the same pack, chronology, overlap and cutoff consistency checks
as `summarize_feature_pack.py`. Output must be a new file. Sources are hashed.
No frozen source or model changes and no training or recording is required.

For fractional per-side fee f and slippage s, the break-even quote log return is
`10000 * log((1+f)*(1+s)/((1-f)*(1-s)))`.
The ask-to-bid target already includes the spread. At 10 and 2 basis points,
the barrier is approximately 24 log-basis-points.

The report subtracts this barrier from the selected mean quote log return.
This descriptive shortfall is not expected cash profit, an execution result,
or a significance test. A positive value would not approve trading. The
per-model selections differ, so their means are not paired comparisons.

Eligibility counts retain the original frozen barrier. Alternative scenarios
cannot recompute those counts from summary statistics. Historical settings
and results are never overwritten. Keep actual account evidence private;
do not commit screenshots, credentials or account identifiers.
