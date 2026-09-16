# Version 1.6.1 — visible observer progress

Adds throttled stderr progress to observer and paper sessions, with startup/connection/retry/shutdown transitions, elapsed/remaining time, message totals and average rate, receipt-fresh quote counts, minimum candle warmup, reconnects/errors, and clock status. `--progress-seconds` defaults to five; zero disables it. Health JSON includes connection state. Output is flushed; broken console output disables reporting instead of triggering reconnections.

This is a patch to the installed 1.6 release, so its version is 1.6.1 rather than 1.5.1. No training, feature, model, accounting, decision-cadence, dataset, or dependency changes are included. The existing default health-write cadence is preserved; explicitly choosing an interval below five seconds also increases health refresh frequency during incoming traffic. Blocking network calls retain their existing timeouts.

Validation: 110 tests run, 109 passed and the optional Numba test skipped. Six new tests cover throttling and forced transitions, quiet mode, invalid intervals, broken output, continuous/retry formatting, and an offline mock WebSocket session that verifies messages, clean stdout, shutdown health, and socket cleanup. No live connectivity or new performance benchmark is claimed.

Updating GitHub cannot change a process on a separate PC. Let current sessions finish before pulling the update; only new launches receive the progress display. See the public Start here guide for options.
