# Historical USD-M funding acquisition

Collect realized funding events for the same August 1–7 development week as the
candle pilot. This is a separate public-data step, not trading or a backtest.

```bash
python -u download_usdm_funding.py \
  --symbol ETHUSDT \
  --start 2026-08-01 --end 2026-08-08 \
  --reserve-from 2026-09-01 \
  --output-dir data/usdm-funding-aug01-07
```

No credentials are sent. The fixed endpoint is
`https://fapi.binance.com/fapi/v1/fundingRate`. End is exclusive locally; the
request uses endTime minus one millisecond. Full pages advance startTime past
the last returned timestamp. Responses must be strictly ordered, unique,
within the requested interval, for the requested symbol, with finite decimal
rates and positive mark prices when provided. Missing marks remain explicitly
missing. Unknown additional API fields remain preserved in the raw response.

Limits: one to seven completed UTC days, eight pages maximum, 1 MiB per response,
1,000 events per page. The existing bounded downloader supplies request timeouts,
retries and disk reserve. Empty history and exhausted page budget fail without
publishing a dataset. An existing destination is refused. Cooperating writers
use a lock; publication stages the directory together, without a power-loss
persistence guarantee. Prior candle datasets are not modified.

Output contains raw pages, normalized `funding.json`, and `summary.json` with
request URLs, SHA-256 hashes, retrieval time, date boundaries, observed intervals,
missing-mark count and runner hash. Unlike public ZIP archives, these API
responses have no exchange-provided checksum; local hashes record what was
received and detect subsequent changes, not source correctness.

`api_pagination_exhausted=true` only describes query termination.
`schedule_coverage_verified=false` is intentional: rates and funding intervals
can change, and this collector does not reconstruct historical interval rules.
Do not fill missing events with zero or assume every eight-hour event exists.
Realized funding cannot be used as a feature before it was available at the
historical decision time. It is not a forecast or account-specific payment.

The output is research-only. Actual position cash flows, mark-price alignment,
fees, contract rules and execution assumptions still need implementation and
validation before evaluating a futures strategy.

## Sources

- [Binance official USD-M market-data documentation](https://developers.binance.info/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data)
  includes funding-history parameters and response fields.
- [Binance official Python connector](https://github.com/binance/binance-futures-connector-python/blob/main/binance/um_futures/market.py)
  documents ascending order and the maximum page size.

The five tests use mocked API pages, including pagination and failed acquisition.
The actual historical query has not been run in the development workspace.
