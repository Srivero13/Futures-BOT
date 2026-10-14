# UM01 unchanged-rule extension

```bash
python -u research_usdm_bundle.py \
  --bundle data/usdm-aug08-31-bundle \
  --output data/usdm-UM01-aug08-31-development.json
```

Runs the existing UM01 plan function without parameter changes over August 8–31.
It retains the odd-hour decision grid, 60-minute close momentum, 20-log-bps
threshold, one-minute entry delay, 60-minute holding period, signed 0.05 ETH,
and hypothetical 5-bps fees and 2-bps impact per side. No optimization, training,
side selection or automatic promotion occurs. The original August 1–7 rejection
remains evidence even if this extension is profitable.

The bundle must match the exact period and market and be complete. Every saved
trade, mark and funding source is re-audited and compared with the manifest hashes.
Funding chunks are concatenated and the accounting engine rejects duplicate or
unordered timestamps. All input hashes are checked again after evaluation.
No downloads occur. Existing result paths are refused.

Positions carry across weekly boundaries. Weekly totals assign each completed
trade entirely to its exit week; they are not mark-to-market returns or four
independent trials. The final chunk is three days. Global drawdown comes from the
continuous sampled P&L path. The first hour supplies signal warmup; August 7 is
not loaded. End-boundary candidates without complete exits are counted separately.

This is additional development evidence, not an untouched validation set.
August spot data has already been inspected in earlier work. There is no margin,
liquidation, executable-fill or verified historical funding-schedule model. The
full report retains the plan, accounting, input hashes and relevant code hashes.
Tests cover weekly attribution at the exact boundary, incomplete-manifest rejection,
fixed costs and permanent unapproved status, alongside existing causality and
sequential-accounting tests.
