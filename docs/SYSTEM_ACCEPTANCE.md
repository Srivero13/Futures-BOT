# Finite system acceptance

Run one integrated host check after updating, rather than repeating individual
research summaries. This assesses the implemented paper/observer software;
it does not establish strategy profitability or finish a live scalping system.

```bash
cd ~/projects/Futures-BOT
git pull --ff-only origin develop
acceptance_dir="data/system-acceptance-$(date -u +%Y%m%dT%H%M%SZ)"
.venv/bin/python -u run_system_acceptance.py \
  --seconds 1800 --output-dir "$acceptance_dir"
```

The output directory must not exist. The command first runs the existing startup
doctor, then exercises two explicitly synthetic virtual accounts in isolated
SQLite files. It checks paused entries, duplicate protection, online backup,
restoration of open positions and duplicate records, flattening while entries
remain paused, and full financial reconciliation. Synthetic quotes are only used
for this engineering control, never substituted for a failed public feed.

It then starts the existing observation-only public stream for 30 minutes.
The health file and final observation result stay in the new run directory.
It never starts paper trading, changes model approval, accesses credentials or
sends exchange orders. Existing portfolio databases and WBC01 artifacts are not
modified. The observer may create the default database's parent directory, as
before, but does not open a portfolio database in observe mode.

`acceptance.json` records the stage and result. Successful full completion is
`finite_engineering_checks_passed`, with `approved=false`. Feed checks require
completion of the requested duration, received messages, stable wall/monotonic
clock comparison, no recorded errors, clean shutdown, 21 closed candles per
configured symbol and final quote ages within 1,000 milliseconds. Missing or
stale quotes are failures even when a socket connected. Errors fail this finite
screen even if a reconnect subsequently succeeded; inspect them before repeating.
Final freshness does not prove continuous coverage, source timestamp freshness,
RTT, exchange fills or order latency. The 30-minute test is not a 24/7 endurance
certification. Existing models remain unapproved and cannot open paper positions.

`--offline-only` performs the doctor and synthetic lifecycle without networking;
its result explicitly says the feed was not tested. It cannot produce a full
engineering pass. Ctrl+C records an interrupted status where possible, never
success. Abrupt power loss can leave a running status; no auto-resume or automatic
ledger repair occurs. Preserve the run output for diagnosis.

## Definition of completion

- This acceptance task is complete once the finite host checks pass and output is
  preserved. It does not require another strategy experiment or GPU training.
- The paper engine has tested controls and accounting, but real-network paper
  decision execution still requires a valid latency profile and eligible model.
- The original profitable live scalping goal remains unvalidated: no after-cost
  edge, eligible deployment strategy or real-order integration is established.
- WBC01-F01 proceeds under its unchanged separate future protocol. It is not a
  blocker for improving or operating the public observer.
