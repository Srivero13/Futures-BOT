# Research review: evidence before another experiment

## Current decision

The development phase has now closed with no promoted candidate. See the
[closeout](DEVELOPMENT_PHASE_CLOSEOUT.md) for the subsequently completed hourly
and every-minute breakout experiments. The original dossier below remains an
accurate record of its narrower scope and is not overwritten.

Keep the evaluated strategies research-only. Software tests, stable collection
and reproducible forecasts are engineering achievements; none establishes a
profitable strategy. Do not treat hours of training or hardware upgrades as a
percentage of progress toward profitability.

The following observations are from operator-supplied development summaries,
not independently reproduced market-data runs in the repository workspace:

| Experiment | Evidence | Disposition |
|---|---|---|
| Frozen microstructure pack | Two captures, 6,776 common rows; baseline selected mean 0.4533 log-bps versus about 24 log-bps costs; zero eligible forecasts | Preserve as a predictive benchmark, not an executable strategy |
| Fixed hourly trend | 63 trades; summed independent-month net +0.5453 USDT; excluding best trade -4.9183; extra 0.5 bps slippage per side -0.0853 | Do not advance on this development result |
| BTC-context comparison | 4,410 paired test rows; richer model beats ETH-only in 2/6 months; pooled RMSE 57.66041 versus zero 57.66216; zero cost candidates | No compelling incremental or economic evidence |

These studies overlap in periods and may use different selected samples. Do not
sum their sample sizes into an independent evidence count, compare headline
RMSE across different targets, or combine their P&L into a portfolio result.

## Target and execution audit

* Microstructure targets are delayed ask-to-bid returns. Spread is already in
  the target. The 10 bps fee and 2 bps slippage per side scenario implies about
  24 log-bps required return.
* Minute-candle targets are delayed reference open-to-open returns. A separately
  assumed 2 bps full spread makes the cost about 26 log-bps, or 28 with the fixed
  2 bps margin used in forecast diagnostics. That margin is not an actual fee.
* Historical closed-candle features assume timely candle availability; receipt
  times and order latency are not established by historical OHLC data.
* Quote-level studies do not prove actual fills. Candle execution assumes full
  fills and fixed costs, without queue position, historical exchange filters or
  intrabar drawdown. Minute delays are scenario choices, not measured latency.
* A residual-quantile buffer is a heuristic under serial dependence and market
  drift. Zero eligible forecasts alone is not a statistical rejection test;
  weak ranking and inadequate gross returns also matter in these results.
* Removing a best trade measures concentration. Trend strategies can depend on
  rare large winners; removal alone does not invalidate them. Cost sensitivity
  and the limited development history reinforce the current lack of evidence.

## Reproducible local dossier

```bash
python review_research.py \
  --pack data/frozen-feature-pack.json \
  --pack-reports data/feature-forward-*/evaluation/report.json \
  --hourly-report data/eth-hourly-trend-development.json \
  --cross-report data/eth-btc-context-development.json \
  --fee-bps-per-side 10 --slippage-bps-per-side 2 \
  --output data/research-review.json
```

The tool validates frozen-pack report consistency, recomputes cross-asset RMSE
from saved predictions and labels, and reruns saved hourly trade accounting and
slippage attribution. It records source hashes and writes a new report. It
cannot independently authenticate or replay the raw market data. It does not
read reserved data or alter models, orders, approval flags or runtime guards.
Fees are explicit scenario inputs; the tool does not verify account rates.

## Conditions for resuming new strategy research

1. Write a mechanism explaining why the input should predict the chosen target,
   and distinguish it from already failed hypotheses. More features alone is
   not a mechanism.
2. Fix data requirements, feature timing, target, benchmark, costs, parameters,
   development budget and failure criteria before testing. Record all attempts.
3. Require an economically material development result with plausible cost
   stress, enough independent periods and uncertainty assessment that respects
   serial dependence. Do not choose thresholds to rescue the six inspected months.
4. Freeze the candidate and protocol before accessing an untouched period.
   Repeatedly inspected "test" periods are development data. A calendar reserve
   is an access boundary, not proof that data has never been seen.
5. Only after independent evidence, test actual execution assumptions and a
   prospective paper ledger. A positive forecast diagnostic is not this stage.

Until a distinct hypothesis and these requirements are written down, pause
additional model variants. Preserve the current artifacts and reserved period;
there is no justified promise of profitability or completion date.
