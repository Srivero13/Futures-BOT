# Daily attribution of a continuous exposure

```bash
python summarize_usdm_days.py \
  --report data/usdm-mark-path-bounds-aug01-07.json \
  --output data/usdm-daily-attribution-aug01-07.json
```

Reads an existing mark-path report without downloading data or placing orders.
Validates every expected minute-close timestamp, entry and exit point, finite
P&L, terminal reconciliation, sampled drawdown and minimum sampled P&L. It also
checks the report's source file hashes before and after attribution. It does not
independently rebuild marks, funding or fills; these remain the upstream audit's
responsibility. Existing output files are refused.

Daily net change is the day's last cumulative P&L minus the preceding day's last
cumulative P&L (zero before entry). Thus entry costs, held funding, unrealized
price changes and final exit costs flow through the same continuous position.
UTC boundaries are used regardless of the operator's local timezone. The last
day contains the realized exit. Daily changes must sum exactly to terminal P&L.

Positive days are not a trade win rate. Best-day removal is an arithmetic
concentration diagnostic, not an executable decision to avoid that day.
The long and short scenarios are separate hypothetical positions; they are not
a combined hedged strategy. No side selection, margin recommendation, annualized
return or strategy approval is produced. Tests cover midnight continuity, costs,
summary inconsistencies, nonfinite data, timestamp gaps and changed input files.
