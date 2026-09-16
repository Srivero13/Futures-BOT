# One-minute model execution backtest

`backtest_v16.py` evaluates existing v1.6 linear or polynomial artifacts against
verified one-minute Binance shards. It is offline, long-only spot research.
It cannot send orders, approve a model, or measure profitability in live markets.
The existing five-minute `backtest.py` remains a separate legacy strategy tool.

## Requirements

Use the project's Python 3.12 virtual environment and pinned `requirements.txt`.
No additional dependencies, GPU, credentials, or network connection are required.
Provide downloaded CSV shards and their `.json` checksum/identity sidecars,
a checksummed model artifact, and sufficient disk space for the JSON report.
Candles stream through a 21-bar window; the report retains one record per trade
and hour, so memory grows with report size rather than total input candle count.

## Run

Replace MODEL_DIRECTORY with the completed training directory:

```bash
python backtest_v16.py \
  --files data/market-expanded/binance-ETHUSDT-*.csv \
  --model MODEL_DIRECTORY/model.json \
  --start 2026-07-01 \
  --end 2026-09-01 \
  --delay-bars 1 \
  --output data/eth-execution-delay1.json
```

Dates are UTC and the end is exclusive. The start must be at or after model
calibration. Supply chronological files including at least 21 preceding candles
for full initial warm-up. Gaps intersecting evaluation and incomplete intervals
fail instead of inventing fills. Output files must be new; existing reports are
not overwritten. Progress appears on stderr every 4,096 evaluated bars, after
input checksum verification. Ctrl+C cancels without publishing a complete result.

## Execution assumptions

- Default starting cash: 1,000 quote-currency units; order notional cap: 100.
- Fees: 10 bps per side. Full spread: 2 bps, charged as half on each side.
- Slippage: 2 bps per side. These are declared assumptions, not fetched account fees.
- Quantity step: 0.000001; minimum notional: 5. Supply the appropriate assumptions
  with `--qty-step` and `--min-notional`; historical exchange filters are not available.
- Signal uses only prior closed candles. A one-bar delay fills one minute after
  the decision boundary at that bar's open plus spread/slippage. `--delay-bars 0`
  is an optimistic same-boundary fill, not a measured low-latency execution.
- One pending entry or position at a time. Exit is scheduled at the open
  `model.horizon_bars` after entry. No entry whose scheduled exit lies outside
  the interval is filled. The exit is predetermined, without future-price access.
- Entry gate uses the model's calibrated lower forecast, exact round-trip
  break-even price ratio, and 2 log-bps margin. It does not force trades.
- Fifty-digit Decimal arithmetic handles accounting and quantity rounding;
  model features and forecasts retain float64 arithmetic. This does not make
  forecasts economically accurate.

The holding period starts at the delayed fill, whereas model labels start at the
next open. Delay therefore introduces target mismatch: treat this as an execution
stress scenario, not a newly calibrated prediction horizon. Minute candles cannot
reconstruct millisecond fills, bid/ask history, queue position, partial fills, market
impact, or intrabar drawdown. The simulator does not reproduce all live portfolio
risk controls. Funding, interest, and infrastructure overhead are excluded.

## Read the report

The report contains net P&L, returns, fees, spread/slippage cost already embedded
in fill prices (do not subtract it twice), closed trades, win rate, profit factor,
open/close sampled liquidation-value drawdown, and hourly marked equity changes.
P&L is in quote-currency units. The no-interest cash baseline earns zero.
Undefined ratios are null, including win rate with no trades and profit factor
without losses. Zero trades means no qualifying simulated executions, not proof
of a profitable or safe strategy. Partial boundary hours are possible.

Input and model hashes are checked before and after the run. The report records
source paths/hashes, model hash, runner hash, dates, and explicit cost assumptions.
Use version control for the associated engine implementation.

Previously inspected July–August 2026 results are retrospective diagnostics.
Do not tune thresholds or costs against this period and relabel it an untouched
holdout. Define future hypotheses and validation boundaries before comparing
alternatives. Reports always remain unapproved; successful backtests do not
promote a model or enable trading.
