# Complete the fixed mark-price week

```bash
python -u batch_usdm_marks.py \
  --first-pilot data/usdm-marks-20260801 \
  --output-dir data/usdm-marks-aug02-07
```

This fixed ETHUSDT August 1–7, 2026 data task first reaudits the existing August 1
pilot. It then downloads August 2–7 into separate dated directories and audits
each day. The original pilot remains in its original location. The new output
directory must not exist. Successful completion reports seven days and 10,080
minutes, including the reused pilot.

Saved-file auditing verifies market/data-kind identity, date/reserve boundaries,
raw-page hashes and size limits, exact pagination URLs, candle validation and
complete normalized conversion. It reuses the downloader parser and does not
constitute an independent price source. All input and report hashes are checked
again before completion. Local hashes are consistency checks, not proof against
wholesale replacement of provenance. No spot/trade candles are modified.

Per-day reports and `status.json` preserve progress. Failure stops further days;
Ctrl+C attempts to record interruption. No automatic resume is implemented.
Abrupt power/process loss may leave status running; that is not completion.
Request and storage bounds come from the one-day collector. No GPU or private
credentials are needed.

This prepares valuation data only. Margin tiers, liquidation behavior, contract
filters and account fees remain unverified. No strategy or risk model is approved.

Seven synthetic tests (collector plus batch/audit) passed. Tests cover conversion
corruption even after updating its hash, wrong identity/date/path, first-day
reuse, failure preservation and collector validation. Actual network acquisition
runs on the operator's machine.
