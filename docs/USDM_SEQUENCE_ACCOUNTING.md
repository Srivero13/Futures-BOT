# Sequential futures accounting

`usdm_sequence_accounting.account_sequence(trades, marks, events, fee_bps,
impact_bps)` is an offline research primitive for one signed position at a time.
It reuses the round-trip and mark-path arithmetic. It does not generate trades,
place orders, fetch data, or select a profitable direction.

Each trade requires a unique `id`, decimal-string `quantity`, `entry_reference`,
`exit_reference`, and integer minute-aligned `entry_ms`/`exit_ms`. Trades must be
chronological. The next entry must be strictly after the preceding exit;
simultaneous reversals are intentionally unsupported until their ordering is
modeled explicitly. Costs are decimal strings in basis points per side.

Marks and funding use the existing normalized schemas. The caller must audit raw
sources, verify market identity, map reference prices to the appropriate candles,
and establish causal signal timing before invoking this primitive. It accepts
supplied reference prices; reconciliation alone does not make those prices
executable or demonstrate a strategy edge.

The result includes separate price, impact, fee and funding totals, each trade's
accounting, and a continuous cumulative P&L path. Realized P&L carries into the
next trade without resetting capital. Funding outside held periods is unassigned;
ambiguous boundary events fail, and no event can be assigned twice. Missing marks
while a position is held fail. Flat-period gaps in marks are allowed. Continuous
sampled drawdown carries the preceding high-water mark across trades. It is not
the sum of per-trade drawdowns. The result deliberately has no ROI, initial
capital, sizing, margin, liquidation, exchange-filter or approval decision.

```bash
python -m unittest discover -s tests -p 'test_usdm_sequence.py' -v
```

Tests use synthetic long and short trades with exact known totals. They cover
funding while flat, costs, cumulative drawdown, overlapping transitions, duplicate
identities/events, missing marks, settlement ambiguity and decimal input checks.
These are accounting tests, not market performance results. Historical rule
experiments must separately implement causal signal selection and retain all
failed development trials before using untouched evaluation data.
