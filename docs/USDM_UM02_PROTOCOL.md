# UM02: fixed four-hour channel breakout

Hypothesis: a breakout beyond a preceding four-hour price channel, held for four
hours, might capture a larger move relative to round-trip costs than UM01's
one-hour momentum rule. This is a hypothesis to falsify, not evidence of an edge.
Earlier spot breakout failures and the UM01 rejection remain in the research history.

Fixed development protocol:

- Use the existing August 8–31, 2026 ETHUSDT USD-M bundle. This period is already
  inspected development data, not independent validation. No September data.
- Evaluate every closed one-minute candle while flat, after 240 warmup minutes.
  Go long only when its close exceeds the preceding 240 candles' maximum high;
  go short only when its close is below their minimum low. Strict comparisons;
  the signal candle is excluded from the channel. Wicks alone do not trigger.
- Decide at candle end. Enter at the next minute's open, 60 seconds after the
  decision, hold 240 minutes, and exit at that reference open. No trailing exit,
  stop optimization, volume filter, side selection or parameter search.
- Use signed 0.05 ETH, hypothetical fees of 5 bps and combined spread/slippage
  impact of 2 bps per side. The separate stress scenario uses 3 bps impact with
  the same trades and quantities; it does not reselect trades.
- Reject candidate entry/exit times within two minutes of the fixed UTC
  00:00/08:00/16:00 grid. This is a declared accounting convention, not a verified
  funding schedule. Actual recorded funding events inside holds are included.
  Unexpected settlement ambiguity fails rather than silently omitting payments.
- Keep one position at a time. A candidate without a full terminal window is
  disclosed and occupies the remaining hypothetical holding interval; its P&L
  is not imputed as zero. The completed-trade total excludes that candidate.

```bash
python -u research_usdm_breakout.py \
  --bundle data/usdm-aug08-31-bundle \
  --output data/usdm-UM02-development.json
```

Retain the full trade plan, component accounting, input/code hashes, continuous
sampled drawdown, exit-week totals and best-trade removal sensitivity. Weekly
figures allocate whole trades to their exit week, not mark-to-market performance.
The loader currently prints `[UM01-bundle]` during shared data audits; this names
the reused loader, not the evaluated rule. Accounting prints `[UM02]`.

Budget: one configuration and one specified impact stress. A failed run is retained,
not inverted or retuned on August. A positive run still cannot establish robustness
or justify live orders. There is no capital sizing, margin, liquidation, exchange
filter, measured fill or historical funding-completeness model.
