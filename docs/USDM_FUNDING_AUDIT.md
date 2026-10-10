# Funding integrity and reference-grid audit

Run after funding collection. No network or trading calls are made.

```bash
python audit_usdm_funding.py \
  --funding-dir data/usdm-funding-aug01-07 \
  --symbol ETHUSDT --start 2026-08-01 --end 2026-08-08 \
  --reserve-from 2026-09-01 \
  --output data/usdm-funding-audit-aug01-07.json
```

The audit verifies identity, page hashes/size limits, exact request pagination,
raw event validation, normalized records, and summary counts and intervals.
Input hashes are rechecked after processing. Existing reports are not overwritten.
The parser is reused from the collector, so this is not an independent source
or parser implementation. Local hashes are consistency checks, not authenticity
proof against deliberately rewritten provenance.

The reference grid has UTC slots at 00:00, 08:00 and 16:00 with a fixed tolerance
of 1,000 milliseconds. This is an explicit diagnostic assumption motivated by
the operator's observed roughly eight-hour intervals. It is not a historical
contract schedule. Missing slots, multiple events in one slot and off-grid events
are reported separately. One event per slot is required for reference-grid
completion. Original event timestamps are never rounded or rewritten.

A seven-day interval has 21 reference slots. A matching count alone is insufficient:
all slots must have one event within tolerance. Even a passing grid leaves
`schedule_coverage_verified=false` and `approved=false`. Do not use the diagnostic
grid to decide whether a position owed a funding payment. Later accounting must
preserve actual timestamps and document its boundary convention.

Four new synthetic tests cover millisecond jitter without mutation, missing and
duplicate slots, off-grid events, rehashed normalized-data tampering, wrong symbol
and raw-page corruption. Together with the five collector tests, nine tests pass.
The actual operator dataset has not been independently audited in this workspace.
