# BASIS-D01: descriptive spot–futures price-difference study

Question: on the already inspected August 1–7 development week, how large and
variable is the ETHUSDT futures/spot close-price difference, and how does it
change at fixed 15- and 60-minute horizons? A later hypothesis could test whether
observable price differences predict convergence sufficient to cover both legs'
costs. This study cannot establish that hypothesis or make an arbitrage claim.

Budget: one fixed seven-day diagnostic, two predefined horizons, no thresholds,
side selection, parameter search or model fitting. Use every complete hourly
anchor and the same anchors for both horizons, purging the last 60 minutes.
Report basis as `10000 * (log(futures_close) - log(spot_close))`, its distribution,
future changes and descriptive correlation with the starting basis. No result
promotes a strategy, triggers training or automatically expands the sample.

```bash
python -u diagnose_usdm_basis.py \
  --first-pilot data/usdm-pilot-20260801 \
  --batch-root data/usdm-aug02-07 \
  --spot-root data/market-expanded \
  --output data/usdm-basis-development.json
```

The command audits the existing futures archives, conversions and spot sidecars;
requires exact minute alignment; and rechecks source hashes before publishing.
No downloads or credentials are needed. The hourly anchor refers to a candle's
open timestamp; its close is only available after that minute ends.

Candle close trades on the two markets need not occur simultaneously. Neither a
basis change nor correlation is executable P&L. Missing prerequisites for a
strategy study include synchronized available bid/ask observations, both-leg
execution and legging assumptions, verified applicable fees, funding timing,
capital/financing and contract constraints. Until those are addressed, no
hedged backtest or live execution should be inferred from this report.

August remains development data; UM01 and UM02 remain rejected. September stays
reserved and is not opened by this command. Before any new executable strategy
experiment, freeze its full causal protocol and chronological development and
untouched evaluation periods. This diagnostic does not supply independent
validation and does not justify selecting a profitable historical interval.

## Reported outcome and disposition (2026-10-14 UTC)

The operator supplied the completed `data/usdm-basis-development.json` summary:

| Metric | Result |
|---|---:|
| Aligned minutes | 10,080 |
| Common hourly anchors | 167 |
| Mean basis | -4.664711 log-bps |
| Minimum / maximum basis | -7.850663 / -1.869633 log-bps |
| 15-minute change minimum / maximum | -2.202215 / 2.325176 log-bps |
| 60-minute change minimum / maximum | -1.664109 / 2.171882 log-bps |
| 15-minute initial-basis/change Pearson correlation | -0.574691 |
| 60-minute initial-basis/change Pearson correlation | -0.549708 |
| Closer to zero after 15 / 60 minutes | 83 / 81 of 167 |

These are operator-reported outputs, not independently reproduced market results
in CI. The full local report retains input and code hashes. The maxima describe
this sampled week and anchor grid; they are not bounds on other observations or
future opportunities.

All observed basis levels were negative: the futures candle close was below the
spot candle close. A persistent discount is not itself a profit or evidence that
the prices will converge to zero. Absolute changes at the sampled horizons were
small, and there are no executable-price observations or verified two-leg costs.

The negative correlations require particular care. Writing basis as B, the
identity `Cov(B_t, B_(t+h)-B_t) = Cov(B_t, B_(t+h)) - Var(B_t)` shows that the
starting value is also subtracted inside the change. Even independent successive
basis levels with equal finite variance give correlation `-1/sqrt(2)` between
level and change. The reported negative correlations alone therefore do not
establish exploitable convergence, a half-life, significance or after-cost profit.

Disposition: diagnostic complete, no strategy candidate advanced. No thresholds,
long/short selection or model fitting will be chosen from this week. This does
not reject every possible basis strategy; it means this diagnostic has not
supplied executable evidence to justify one. UM01 and UM02 remain rejected.
