# Consolidating frozen evaluations and verifying costs

```bash
python summarize_feature_pack.py \
  --pack data/frozen-feature-pack.json \
  --reports data/feature-forward-*/evaluation/report.json \
  --output data/frozen-feature-pack-summary.json
```

The summary requires the same pack hash, unchanged cutoffs and compatible builder
provenance. Duplicate captures and overlapping reported time ranges are rejected.
RMSE is pooled from sample-weighted squared errors. Selected means are weighted
by selected counts; those subsets differ by model. Correlations stay per capture.
The summary validates report consistency, not raw data or predictions independently.
It writes a new output and does not change the frozen pack or any hashed source.

## Account cost evidence

The existing 10 bps fee and 2 bps slippage per side are research assumptions.
No account-specific rates have been verified. These captures are Binance SPOT
ETHUSDT; they cannot validate a futures strategy or its funding/execution costs.

Binance's official Spot Commission FAQ documents `GET /api/v3/account/commission`
and `account.commission` for current account/symbol rates. Its example numbers
are explicitly fictional. Rates can include standard, tax and special commission;
standard commission may have conditional discounts. Buy/sell and maker/taker
components matter. Fee payment asset also affects realized accounting.

Reference, reviewed 2026-09-24:
https://github.com/binance/binance-spot-api-docs/blob/master/faqs/commission_faq.md

Before revising costs, record the actual market, symbol, maker/taker rates,
applicable buy/sell components, discount eligibility and fee-payment asset from
your own account. For this taker-style simulation, maker rates cannot simply be
substituted: maker execution would require a separate fill/queue model.

Do not put API keys, secrets, account identifiers or balances in reports or Git.
Only fee rates and relevant conditions are needed for this discussion. The tool
makes no authenticated request and sends no orders. Keep historical frozen
assumptions intact; any account-specific scenario should be separately labeled.
