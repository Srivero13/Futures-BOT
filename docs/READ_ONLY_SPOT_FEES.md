# Local read-only Spot fee query

This optional tool queries current account/symbol commission rates for the Spot
market used by existing research. It does not select a market or enable trading.

```bash
python read_spot_fees.py --symbol ETHUSDT --output data/spot-fees-ETHUSDT.json
```

Run in an interactive Ubuntu terminal. It prompts privately for an existing
read-only HMAC API key and secret. Credentials never belong in chat, shell command
arguments, report files or Git. No trading or withdrawal permission is needed;
do not enable either for this tool. RSA and Ed25519 keys are not supported.
If you do not have a suitable key, provide just the fee rates shown in your
Binance account instead. There is no need to create a trading-enabled key.

Only two GET endpoints on https://api.binance.com are used: public server time,
then `/api/v3/account/commission`. TLS certificate validation is enabled; redirects
and environment proxies are disabled. Network calls have ten-second timeouts.
No order, test-order, balance or transfer endpoint is called. Errors omit request
URLs, signatures, headers and response bodies. Hidden-input fallback is refused.

Output contains only the requested symbol, standard/tax/special commission
components, discount flags/asset/value, and query time. Unknown response fields
are discarded. Rates are raw decimal fractions: 0.001 means 0.1%. The tool does
not apply discount arithmetic or assume a sufficient BNB balance. It does not
modify frozen assumptions or claim effective fees have already been calculated.
Python process memory is not securely erased; credentials exist there during use.

Official endpoint reference, checked 2026-09-24:
https://developers.binance.com/docs/binance-spot-api-docs/rest-api/account-endpoints

Account-specific live access requires the user's own credentials and is not
covered by mocked offline tests. Output files must be new. Futures commissions
and funding require a separate market-specific analysis.
