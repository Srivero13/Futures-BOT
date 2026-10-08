# Saved USD-M pilot audit

The operator reported successful acquisition of all 1,440 ETHUSDT minute
candles for August 1, 2026. This command rechecks the files on the operator's
machine and aligns them with the existing August spot shard. No download,
training, API credentials or trading is involved.

```bash
python -u audit_usdm_pilot.py \
  --pilot-dir data/usdm-pilot-20260801 \
  --spot-file data/market-expanded/binance-ETHUSDT-2026-08.csv \
  --symbol ETHUSDT \
  --date 2026-08-01 \
  --reserve-from 2026-09-01 \
  --output data/usdm-pilot-alignment-20260801.json
```

The report path must be new. Success requires the futures metadata and saved
hashes to match, archive revalidation, exact conversion equality for every CSV
field, and all 1,440 timestamps to occur in the validated spot shard. Input
hashes are checked again after processing and recorded in the report. Input
files are not modified. A changed or invalid source stops the audit.

The audit reuses the ingestion archive validator; it is not a second independent
parser. Spot integrity is checked against its local provenance sidecar, not a
redownload of the original spot archive. Local hashes are consistency evidence,
not protection against someone deliberately replacing all provenance records.

Matching minute timestamps does not mean last trades occurred simultaneously.
No equality of spot/futures prices or volumes is expected. This audit deliberately
makes no basis, arbitrage, funding, executable-price or profitability claim.
Futures fees, mark prices, funding and contract rules still require their own
research treatment. All outputs remain unapproved.

Tests include exact alignment without input mutation, a price change with an
updated converted-file hash, a missing spot minute with an updated hash, wrong
venue, archive corruption and reserved-date rejection. Tests use synthetic data;
the user's market-data audit has not been independently run in the workspace.
