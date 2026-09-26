# Every-minute breakout variant

This is a separate development experiment prompted by the outcome-free sampling
audit. The original hourly strategy and its report remain unchanged. The audit
counted 717 qualifying minutes but only five on the hourly grid in the supplied
March–August dataset. That does not imply 717 independent or profitable trades.

## One intentional change

Evaluate the same strict 24-hour breakout condition after **every closed minute**,
instead of only at UTC hours. Do not search different clock phases or sampling
frequencies for profitable historical scores.

All other rules from [the original protocol](DAILY_BREAKOUT_PROTOCOL.md) remain:
prior 1,440 highs excluding the signal candle, one-minute delayed entry,
240-minute hold from entry, one position at a time, long-only, 100 USDT target
notional, 1,000 monthly starting capital, 10 bps fees per side, 2 bps slippage
per side, 2 bps full spread, quantity rounding and minimum-notional assumptions.
Signals while pending or holding do not open extra positions. A new valid signal
after an exit may schedule a new entry one minute later.

Failure screens are reused directly from the hourly module: require at least
30 trades, four positive months, positive P&L excluding the best trade, and
positive P&L with an extra 1 bps slippage per side. Passing is not significance,
profitability proof or model approval. No thresholds are optimized in this run.

## Run

```bash
python -u research_minute_breakout.py \
  --files data/market-expanded/binance-ETHUSDT-*.csv \
  --output data/eth-minute-breakout-development.json
```

The date range is fixed to March–August 2026. September remains excluded.
The runner writes a distinct protocol and report, refuses existing output, and
records source and code hashes. It includes trades, monthly results, best-trade
removal and fixed-quantity slippage sensitivity. No API key or GPU is required.

The high-watermark queue is bounded and updated in amortized constant time per
candle, avoiding a new 1,440-price scan for each decision. Tests compare it with
brute force, verify an off-hour signal is evaluated causally, and verify unchanged
fill accounting for a signal shared with the original hourly strategy.

## Limits

This variant was designed after inspecting sampling and strategy results. It
therefore remains adaptive, retrospective development, not independent evidence.
Existing fill, drawdown, fee, slippage and historical-data-availability limitations
still apply. More observations can be correlated; more trades can mean more
costs. All results remain unapproved, and the runner sends no orders.
