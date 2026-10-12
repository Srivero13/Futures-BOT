# Resumable development data bundle

```bash
python -u collect_usdm_bundle.py \
  --start 2026-08-08 --end 2026-09-01 \
  --spot-root data/market-expanded \
  --output-dir data/usdm-aug08-31-bundle
```

Collects 24 days (34,560 minutes per candle series) of ETHUSDT USD-M traded-price
and mark-price candles, plus four funding chunks of at most seven days. Dates
are UTC and the end is exclusive. Only acquisition and audits run; there are no
signals, model training or orders. August already belongs to development data.
September 1 onward remains excluded. No API key is required.

The collector accepts 1–31 completed days ending no later than September 1, 2026.
It requires local spot shards and their sidecars. Existing bounded downloaders
provide archive/page limits and request timeouts. Downloads are sequential;
there is no promise the work will last a fixed number of hours.

If interrupted, run the exact same command. The bundle identity must match,
including the resolved spot input directory. Existing trade, mark and funding
folders are re-audited; only missing folders are downloaded. Corrupt existing
folders fail rather than being overwritten or silently repaired. An unrelated
existing output directory is refused. A cooperating process lock prevents two
bundle collectors from writing the same destination concurrently.

`bundle.json` records progress and completion. Completed source downloads survive
failure. Abrupt termination can leave status `running`; it does not imply an
active process. A final pass rechecks all source hashes before `complete` is
written. Initialization failure before a manifest exists is not automatically
recoverable; use a new output directory and preserve the incomplete one.

Folders are `trades/YYYY-MM-DD`, `marks/YYYY-MM-DD` and
`funding/CHUNK-START-DATE`. Funding audit integrity is not proof of historical
schedule completeness. Marks are valuation references, not executable quotes.
This collector does not alter UM01's rejected status or establish a new edge.

Tests use synthetic downloads to cover interrupted acquisition and resume,
complete-run reuse, corruption rejection, identity/reserve guards and 24-day
funding chunk boundaries. Actual network collection runs on the operator's PC.
