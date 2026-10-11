# Fixed-exposure mark-price P&L path

`diagnose_usdm_mark_path.py` reaudits the seven trade-price days, funding responses,
spot alignment and seven mark-price days. It values separate +1 and -1 ETH
exposures from August 1 00:02 to August 7 23:58 UTC, using the same hypothetical
fills and costs as the fixed round-trip diagnostic. No new data is downloaded.

```bash
python -u diagnose_usdm_mark_path.py \
  --first-pilot data/usdm-pilot-20260801 \
  --batch-root data/usdm-aug02-07 \
  --spot-root data/market-expanded \
  --funding-dir data/usdm-funding-aug01-07 \
  --marks-first data/usdm-marks-20260801 \
  --marks-batch data/usdm-marks-aug02-07 \
  --fee-bps 5 --impact-bps 2 \
  --output data/usdm-mark-path-aug01-07.json
```

Five fee bps and two combined spread/slippage bps per side are hypothetical
assumptions, not verified account costs. The first point charges entry fees only;
entry impact appears when valuing against the first mark close. Subsequent points
use signed quantity times (mark close minus assumed entry fill), plus cumulative
held-period funding and minus entry fees. Funding enters at the first minute close
at or after its original millisecond timestamp. Exit realizes assumed exit fills
and exit fees. Final P&L must reconcile exactly with the round-trip result.

The saved JSON includes the full path, input hashes and summary for each side.
Drawdown starts from a zero-P&L reference and uses only these sampled points.
It is not full intraminute drawdown. No initial capital, percentage return,
maintenance margin, liquidation, exchange rounding or trade selection is modeled.
Ambiguous funding boundaries, missing held-period minutes, changed inputs and
terminal mismatches fail the calculation. Historical funding schedule completeness
remains unverified. Existing output files are refused.

Tests use synthetic marks and funding to verify signs, settlement timing, terminal
reconciliation, drawdown, missing data and ambiguous or duplicate funding rejection.
Actual market results must be calculated with the operator's audited files.

## Bounds from minute high/low marks

The report also provides `ohlc_drawdown_upper_bound_quote` and
`ohlc_pnl_lower_bound_quote`. For each held minute it combines the low/high mark
P&L with the minimum/maximum cumulative funding state reached during that minute.
This includes intermediate funding debits even if a later credit cancels them.
For short positions the high mark is adverse; for long positions the low is adverse.
The drawdown bound allows the favorable extreme to precede the adverse extreme
within a minute, because OHLC does not identify their ordering. It also includes
entry fees and the terminal realized exit.

These bounds may overstate actual losses: price extrema and funding states need
not occur together. They are conditional on the supplied marks and funding being
complete, the fixed exposure remaining open, and the stated cost assumptions.
They are not a margin requirement, safe deposit amount, or liquidation calculation.
The previous close-only drawdown is retained for comparison. No new strategy or
side is selected from these results.

Use a new output name, such as `data/usdm-mark-path-bounds-aug01-07.json`, to keep
the original report. Tests cover intraminute excursions invisible in closes,
long/short signs, a debit followed by a credit in one minute, and invalid extrema.
