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
