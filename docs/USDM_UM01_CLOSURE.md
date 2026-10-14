# Close UM01 development evidence

```bash
python close_usdm_experiment.py \
  --first-report data/usdm-UM01-development.json \
  --extension-report data/usdm-UM01-aug08-31-development.json \
  --output data/usdm-UM01-closure.json
```

Reconciles both saved runs using the existing evidence reviewer, checks source
hashes, unique trade identities, chronological nonoverlap and expected August
windows, then adds accounting components with Decimal arithmetic. A rejected
input run remains rejected in the combined record even if another period wins.
No positive total produces automatic approval. Reports are preserved.

The operator reported 35 trades with -8.183298369928794455 USDT in August 1–7
and 159 trades with -17.928389902299040590 USDT in August 8–31. The latter's
four exit-week totals were -2.041137787195780615, +8.381618922742548550,
-20.200962286342982665 and -4.067908751502825860. The closure command checks
local evidence rather than treating these transcribed figures as verified files.

This closes UM01 as a failed development hypothesis under the stated costs.
Do not automatically invert it, lower its costs, select a favorable week, or
optimize it repeatedly on this period. New research must state a new hypothesis
and evaluation protocol before examining its results. Reusable ingestion and
accounting infrastructure is progress in engineering, not evidence of an edge.

The aggregate is the sum of two separate runs with their own warmup and boundary
exclusions. It is not a continuous August portfolio or a compounded return.
Drawdowns are intentionally not added or promoted to a combined figure. The
full trade records remain available. Source hashes establish local consistency,
not independent reconstruction of signals or exchange execution.
