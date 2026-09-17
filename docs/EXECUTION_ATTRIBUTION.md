# Attribution of saved reversal executions

`attribute_v16.py` explains the saved reversal trades without rerunning entry
selection or changing the strategy. It is offline and requires the original
experiment JSON, the same verified source shards in the same order, and the base
Python requirements. Source paths can move; content hashes must match.

```bash
python attribute_v16.py \
  --report data/eth-normalized-reversal-development.json \
  --files data/market-expanded/binance-ETHUSDT-*.csv \
  --output data/eth-reversal-attribution.json
```

The tool loads candle opens only for executed decision, entry and exit timestamps.
It rejects source checksum/provenance mismatches, shards extending into the
reserved period, missing opens, duplicate trades, incorrect timing, and saved
fills/costs that do not reconcile within 1e-18 quote units. Inputs are rehashed
before publishing and existing output reports are not overwritten. No model,
strategy, original report or source candle is changed.

For quantity q and reference opens S (signal boundary), E (entry), X (exit):

- Delay price change at the same quantity: q × (E − S).
- Gross holding P&L: q × (X − E).
- Net P&L: gross holding P&L − fees − spread/slippage cost.

The delay amount is **not realized profit or loss**. Positive means price rose
before entry; negative means it fell. Holding quantity and exit fixed is an
attribution convention, not an earlier-entry backtest: an earlier entry could
change sizing, exits, available trades and execution feasibility. The signal
reference is a candle open, not a quote guaranteed executable after signal
computation. The one-minute delay is an assumed scenario, not measured RTT.

Reports contain per-trade amounts and log returns, monthly aggregates and totals.
Mean log returns equally weight trades; monetary sums use actual executed
quantities. A sum of log returns is not presented as a portfolio return. Months
retain their independent cash resets. No confidence interval, causal latency
claim, hardware recommendation or promotion follows automatically from these
numbers. Only executed trades are included; rejected opportunities are absent.

After completion, paste the printed summary and monthly results. Inspect whether
price movement concentrates before entry, during holding, or neither. Keep the
failed strategy result and reserved period unchanged while interpreting this
retrospective diagnostic.
