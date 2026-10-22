# NautilusTrader integration — first working milestone

The isolated integration uses NautilusTrader 1.231.0, tested with Python 3.12 on
Linux x86-64. Its Linux wheel requires glibc 2.35 or newer (Ubuntu 22.04+).
Use a separate environment: existing CPU/GPU research dependencies are unchanged.
The pinned dependency set is in requirements-nautilus-lock.txt. Other platforms
need separate compatibility verification. NautilusTrader is LGPL-3.0 licensed;
retain upstream notices and review its terms before distributing modified builds.

## Run the offline accounting control

From the repository root:

```bash
python3.12 -m venv .venv-nautilus
.venv-nautilus/bin/python -m pip install -r requirements-nautilus-lock.txt
.venv-nautilus/bin/python -m unittest discover -s tests_nautilus -v
.venv-nautilus/bin/python -m integrations.nautilus.control \
  --output "data/nautilus-control-$(date -u +%Y%m%dT%H%M%SZ).json"
```

No API keys, network requests, real orders or market downloads are used by this
control. Installation requires package downloads. The replay should finish in
seconds; it is not an overnight training task.

Two separate BacktestEngine instances represent isolated spot cash accounts.
Each buys one synthetic ETH at ask 100.10 and sells at bid 101.00 or 99.00,
with explicit hypothetical 10 bps fees, zero added slippage and zero latency.
Actual Nautilus fills and commission currency are checked, not only totals.
The same quotes and decisions are replayed through engine_v1.core.Portfolio.
Both engines must be flat and their fees/cash must equal independent Decimal
arithmetic. Expected final cash: 1000.6989 and 998.7009 USDT respectively.
A failed check raises an error; no success report is written. Existing reports
are refused. Unexpected Nautilus versions fail before simulation.

This is simulation compatibility, not live multi-account routing or evidence of
profitability. The SIM instrument is deliberately synthetic; its precision and
fees are not claimed to represent current Binance contract specifications.
There is no futures margin, liquidation, funding, queue position or latency model.
Pandas may emit an upstream Timestamp.utcnow deprecation warning; it does not
change the accounting result.

## Migration boundaries

Keep frozen WBC01 files, registrations, source data and previous failed research.
Reuse provenance validation, causal features, research protocols and cost/risk
checks. New integration modules live under integrations/nautilus; the existing
paper engine remains an independent accounting reference during migration.
Do not copy its order lifecycle into Nautilus or treat a model's approval field
as approval for a new execution path.

Following this control, import audited historical candles with explicit close
availability timestamps and venue identity. Check count, precision, gaps and
source hashes against the existing ingestion. Candle replay cannot establish
order-book fills. Then validate public-feed observation and simulated execution,
reconnect/stale-data behavior, isolated account state and global exposure caps.
Live clients and credentials are outside this milestone.

The official website may show 2.x examples. This integration was exercised
against the installed 1.231.0 API; do not mix those APIs or upgrade silently.
