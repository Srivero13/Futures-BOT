# Fixed-week exposure attribution

This diagnostic combines futures reference-price movement and funding for the
fixed August 1–7, 2026 pilot week. It reports separate hypothetical constant
+1 ETH and -1 ETH exposures. Neither side is selected as a strategy.

```bash
python -u diagnose_usdm_exposure.py \
  --first-pilot data/usdm-pilot-20260801 \
  --batch-root data/usdm-aug02-07 \
  --spot-root data/market-expanded \
  --funding-dir data/usdm-funding-aug01-07 \
  --output data/usdm-exposure-aug01-07.json
```

All seven futures days are reaudited against their archives and spot timestamps.
Funding is reaudited against raw responses. Input hashes are checked again
before results are returned. The existing batch status is not trusted as a
substitute for daily validation. Output must be a new file.

For the long, reference-price movement equals the last candle close minus the
first candle open, multiplied by one ETH. The corresponding funding total is
added. The short reverses both components. Figures are USDT, before trading
costs. This is valuation attribution for an assumed existing exposure at every
funding event, including the first event. It is not an entry at the first candle
open. Boundary ambiguity in actual entries/exits remains unresolved by this
scenario and must be handled when a position simulator is introduced.

Candle prices are neither guaranteed fills nor a mark-price equity series.
The report excludes fees, spread, slippage, margin, liquidation, exchange rounding
and position sizing. It provides no capital-return estimate or profitable-side
recommendation. Funding schedule coverage remains unverified. A positive funding
receipt may accompany a larger adverse price move.

Four tests check sign/accounting, flat prices and invalid inputs, fixed-week
orchestration, and stopping on failed audits. Orchestration tests mock data;
actual market-data attribution is run on the operator's PC.
