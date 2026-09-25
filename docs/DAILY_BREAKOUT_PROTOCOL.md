# Experiment: 24-hour breakout with a four-hour hold

## Mechanism and distinction

Hypothesis, not an established market fact: a close above an entire preceding
day's trading range may indicate sustained buying rather than a momentary
best-quote imbalance. If continuation lasts hours, the gross move might cover
the same per-trade costs more readily than a five-second move. This can also
fail through false breakouts and reversals; longer holding alone gives no edge.

This differs from the earlier normalized 20-minute momentum rule: the trigger
is a strict 24-hour range breakout, not a calibrated momentum percentile, and
the holding period is four hours. It is long-only and has no trained model.

## Fixed protocol before this run

* ETHUSDT Binance Spot, one-minute candles; inspect signals only on UTC hours.
* Compare the latest closed minute's close with the maximum high of the 1,440
  bars preceding that signal bar. The signal bar is excluded from the maximum.
* Enter only on a strictly higher close, one minute after the decision, at the
  reference open plus assumed price impact. Never use the current bar's close
  to make its opening decision.
* Hold 240 minutes from entry; exit at that minute's reference open less impact.
  At most one position, no pyramiding and no stop-loss optimization.
* Reset capital to 1,000 USDT monthly; target 100 USDT entry notional. Round
  quantities down using the existing hypothetical 0.000001 step and 5 USDT minimum.
* Fees 10 bps per side, adverse slippage 2 bps per side, full spread 2 bps.
  The inherited cost schema's 2 bps forecast margin is unused: this rule is not
  a return forecast and has no forecast gate.
* March–August 2026 only; September excluded. Require preceding warm-up data,
  checksummed symbol-specific shards and complete minute coverage in each fold.
* One fixed configuration. No variants of the lookback, hold, threshold,
  direction or instrument are included in this experiment's budget.

The runner records source and code hashes and this protocol before evaluating.
These months were inspected by other experiments; writing a protocol now does
not turn them into an untouched test set or remove multiple-testing effects.

## Development failure criteria

Report insufficient development evidence if any of the following holds:

* Fewer than 30 completed trades across the six months.
* Fewer than four positive months under the base costs.
* Total net P&L is nonpositive after removing the single best trade.
* Total net P&L is nonpositive with an additional 1 bps slippage per side.

These are deliberately fixed engineering screens, not statistically derived
confidence levels. Even satisfying all four does not approve a strategy. It
would require a frozen prospective protocol, independent data, dependency-aware
uncertainty and execution validation. A failed screen is not an invitation to
retune this configuration on these months.

## Run once on existing development files

```bash
python -u research_daily_breakout.py \
  --files data/market-expanded/binance-ETHUSDT-*.csv \
  --output data/eth-daily-breakout-development.json
```

Output/protocol paths must be new. Progress is printed during every month.
The report includes complete trades, fees, sampled drawdown, best-trade removal
and 0/0.5/1/2 bps extra-slippage sensitivity in this one run. No separate
diagnostic run, GPU, API key, download or change to earlier models is required.

## Execution limits

Full fills and cost rates are assumptions. No historical order book, partial
fills, exchange filter history, financing, taxes or infrastructure costs are
modeled. Marked drawdown samples opens/closes and omits intrabar extremes.
Unsettled positions or evaluation gaps cause failure, not invented exits.
Late-month candidates are left unfilled when their exit would cross the boundary.
Slippage scenarios hold quantities and selected trades fixed and recalculate
fees; they are attribution, not new portfolio simulations. Sum of monthly P&L
is not a compounded six-month return. All outputs remain unapproved.
