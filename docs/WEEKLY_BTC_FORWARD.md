# WBC01-F01 prospective evaluation registration

The operator verified seven frozen files in
`data/WBC01-frozen-20261021T034750285641Z`. The minute replay reconciled all
three scenarios. Base minute drawdown was 3.70737%, with OHLC upper bound
3.72598%; stress 3.71350%/3.73211%; buy-and-hold 13.07989%/13.10975%.
These are operator-reported development results, not independent validation.
The original frozen protocol's `protocol_only_not_evaluated` field records its
creation state; do not edit that historical file to update experiment status.

The separate `research_protocols/weekly_btc_forward_v1.json` defines a fixed
26-week future observation window: 2026-10-26 00:00 UTC through 2027-04-26
00:00 UTC exclusive. The first decision is Monday October 26, with execution
at 00:01 UTC. Warmup begins October 18 at 23:59 UTC; warmup data may only
initialize the weekly comparison. The terminal reference is April 25 at
23:59 UTC. September is not opened or relabeled untouched.

This duration is a declared observation budget, not a claim of statistical power
or a deadline for finishing the scalping project. At the observed development
trade frequency it may produce few round trips. Report insufficient evidence
rather than automatically extending the window until a positive result appears.

A separate 1,000 USDT hypothetical cash account starts flat. Preserve the exact
rule, 100 USDT entry budget, assumed costs, stress case and baselines. Evaluate
once after the complete interval; interim checks concern data integrity only.
Do not alter thresholds or select a side based on interim returns. Positive
base/stress/ex-best results only merit further review; concentration, sample
size, baseline comparison and execution limitations still matter. No automatic
promotion, real orders or live paper execution are authorized by this protocol.

## Register locally before the window starts

```bash
.venv/bin/python register_weekly_btc_forward.py \
  --snapshot data/WBC01-frozen-20261021T034750285641Z \
  --output data/weekly-btc-WBC01-forward-registration.json
```

Registration checks the exact file set and hashes, rule identity, development
screen, report linkage, risk reconciliation and report-to-code hashes. It does
not modify the snapshot or access market data. The output includes the complete
plan and its hash. It refuses an existing output and registration at or after the
start. Local clock/hash checks are not a trusted timestamp authority; retain the
published git protocol and registration together. Never backdate a late attempt.

No daemon or scheduler is installed and no data collection starts. This change
provides registration only; a future evaluator must enforce this registered
plan, source identity and complete data, and preserve the frozen strategy code.
Public archived candles can be acquired later; there is no requirement to keep a
PC running for six months. Such replay remains an assumed-cost reference test,
not evidence of actual fills. The frozen snapshot copies code/reports, not the
large source CSVs: preserve the source data referenced by the development report.

## Consolidated evaluator

`evaluate_weekly_btc_forward.py` now implements one registered evaluation command.
It pins the published forward plan hash, revalidates the development snapshot,
and requires the current strategy, risk replay and dataset helper hashes to
match the frozen copies. It refuses interim performance evaluation before the
fixed end date. It does not dynamically execute code from snapshot paths.

Readiness can be checked now without reading market data:

```bash
.venv/bin/python evaluate_weekly_btc_forward.py \
  --registration data/weekly-btc-WBC01-forward-registration.json --check
```

Expected before April 26, 2027: `waiting_for_fixed_window_end`. This is a readiness
check, not a running job or a profitable strategy result.

After the fixed window ends, supply the complete canonical BTCUSDT one-minute
CSV shards and provenance sidecars covering the warmup and evaluation interval.
Use `--registration`, `--files` and a new `--output` path. The evaluator performs
source hash/identity checks, chronological completeness checks, fixed-rule signal
construction, base/stress/buy-and-hold accounting, minute risk replay and terminal
reconciliation in one run. No separate attribution commands are required.
Full October and April monthly shards are accepted, with edge minutes unscored;
September and unrelated shards are rejected. April monthly data may not be
available until month end; suitable nonoverlapping daily shards can also supply
the interval. No automatic download is performed.

Output remains unapproved even when the economic screen passes. The sample size
and concentration limitations must be reviewed; this command supplies no
statistical significance or actual execution evidence. Preserve the registration
and source shards. Failed or missing data must be repaired without moving dates,
changing rules or reclassifying the evaluation as development to hide a failure.
