# Mark-price data pilot

Collect one day of USD-M mark OHLC separately from traded-price candles. This
supplies a valuation input for future equity-path work, not executable prices.

```bash
python -u download_usdm_marks.py --symbol ETHUSDT --date 2026-08-01 \
  --reserve-from 2026-09-01 --output-dir data/usdm-marks-20260801
```

The public `/fapi/v1/markPriceKlines` endpoint is called with explicit UTC bounds,
one-minute interval and 1,000-row limit. Up to four 1 MiB pages are allowed.
Every minute must appear exactly once in order; timestamps and close times must
match the requested day. OHLC must be positive, finite and internally consistent.
An empty/incomplete day fails without publishing. Existing destinations are
refused. The existing request timeout/retry/disk reserve and a cooperating writer
lock apply. No credentials, live orders or GPU are used.

Raw pages, their URLs/hashes, normalized `marks.json`, and a summary are retained.
`kind=mark_price_1m` and JSON OHLC-only output distinguish marks from tradable
candles. API fields documented as ignored are not treated as trade volume.
Local hashes do not provide an exchange-signed integrity guarantee. Directory
publication is staged but does not guarantee power-loss persistence.

A later consumer must reverify raw pages and conversion before valuation.
Mark OHLC alone does not provide margin rules, maintenance tiers, liquidation
fees, or complete intraminute paths. This pilot does not certify liquidation
simulation or approve a strategy. The actual public response remains to be run
on the operator's machine; three tests use synthetic responses for pagination,
validation, incomplete downloads, reserve enforcement and overwrite refusal.

Source: [Binance USD-M market-data documentation](https://developers.binance.info/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data),
Mark Price Kline/Candlestick Data section.
