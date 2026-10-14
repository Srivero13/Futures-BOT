# Fixed development cost-feasibility audit

This is an optional descriptive study following the closed strategy phase. It
does not reopen rejected strategies, constitute a new trading hypothesis, or
satisfy the requirements for launching a new strategy experiment. Its sole
question is: how often did fixed-grid ETH upward reference moves exceed our
existing cost assumptions?

## Frozen scope and budget

One run on Binance spot ETHUSDT, March 1 through August 31, 2026. This interval
has already been examined extensively and remains development data. September
and later are excluded. Input CSVs and provenance sidecars are verified before
the run and checked for changes afterward. A protocol is saved before outcomes
are calculated; existing protocol/output files are refused.

At each UTC hour, the assumed entry reference is the minute open one minute
later. Exit references are 15 and 60 minutes after that entry. Both outcomes
must finish in the same calendar month. The two horizons use identical anchors.
The 60-minute windows share endpoints but do not overlap in their interiors;
observations can still be statistically dependent. The one-minute delay is an
engineering convention, not a claim about measured execution latency.

Costs remain 10 bps fee per side, 2 bps slippage per side, and 2 bps full spread.
With fee fraction f=0.001 and half-spread-plus-slippage fraction i=0.0003, the
break-even log-return hurdle is:

```text
10000 * log((1+f)*(1+i) / ((1-f)*(1-i))) = approximately 26.00000685 log-bps
```

There is no extra safety margin because this audit measures break-even, not
entry approval. Cost assumptions are not optimized. Each reported net reference
return is the hypothetical sale proceeds divided by the all-in purchase cost,
minus one; it is not a dollar profit or a compounded account return.

## Output and interpretation

The report lists monthly and pooled counts, fractions of upward moves exceeding
cost, reference-return summaries, and the average cost-adjusted long return over
all anchors. Future returns are labels only. No rule is allowed to select only
the subsequently profitable observations.

A high cost-exceeding fraction would not demonstrate predictability or justify
trading. A low fraction would describe how selective a useful predictor must be;
it would not prove that no strategy could work. No significance test, confidence
interval, executable fill simulation, short-selling model, or approved model is
produced. Candle opens do not reveal actual spread, liquidity, queue position,
or fill probability.

Do not select a horizon from this report and call its same-period results
independent validation. Any later predictive experiment still needs a distinct
economic mechanism, written budget, fixed costs and fresh validation plan.

## Run

```bash
python audit_cost_opportunities.py \
  --files data/market-expanded/binance-ETHUSDT-*.csv \
  --output data/eth-cost-opportunity-development.json
```

The fixed period is enforced, and missing minutes fail instead of silently
changing the sample. No GPU, API key, ledger, or new dataset download is needed.

```bash
python -m unittest discover -s tests -p 'test_cost_opportunities.py' -v
```
