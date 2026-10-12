# UM01 evidence review and closure

```bash
python review_usdm_experiment.py \
  --report data/usdm-UM01-development.json \
  --output data/usdm-UM01-review.json
```

This offline review reconciles each saved trade's components, cumulative realized
P&L, side counts and aggregate summaries. It verifies input file hashes and
retains the source report hash. It does not independently reconstruct signals,
fills, funding or drawdown. The output is new; existing reports are never replaced.

Nonpositive net P&L produces `rejected_development`. A positive development result
can only produce `requires_independent_validation`, never approval. Zero-cost
sensitivity includes reference-price P&L plus funding, with fees and assumed price
impact removed. It is hypothetical and is not an available execution arrangement.

## Reported UM01 result

The operator's August 1–7, 2026 development run reported 35 trades (16 long,
19 short), net P&L -8.183298369928794455 USDT, reference-price P&L -3.5785,
fees 3.29333460785, impact 1.31733370, and funding +0.005869937921205545.
Removing the best trade left -8.960341710978794455. These figures were supplied
by the operator; the review command verifies the local saved report.

Disposition: retain this failed experiment. Do not lower its cost assumptions,
reverse its signals, select only its winning side, or tune its threshold on this
week and then call that week validation. No further training run of this fixed
rule is needed to reproduce the same result. This evidence rejects the tested
configuration on this development period, not every possible futures strategy.

The data/accounting pipeline is reusable; a profitable strategy remains
unestablished. Any later hypothesis needs its own written rationale, fixed
protocol, development budget and untouched chronological evaluation. This review
does not authorize live orders or establish account fees, margin or liquidation.

The same command now accepts UM02 reports while preserving the experiment identity.
UM02 additionally checks best-trade removal, exact fixed-cost stress accounting and
exit-week totals. The UM01 closure command explicitly refuses mixed experiments.
