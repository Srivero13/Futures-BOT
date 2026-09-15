# Contributing

Use English for code comments, documentation, issues, and commit messages. Keep changes scoped and describe both behavior and validation evidence. This project currently supports research and paper workflows; do not describe simulated results as live execution.

## Development environment

Fork or clone the repository, then create a branch for the change. On a host meeting the [requirements](docs/REQUIREMENTS.md):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Install `requirements-fast.txt` to exercise the optional compiled backend. Without it, the optional Numba test is skipped. The system installation script targets Ubuntu and requires sudo; the virtual-environment commands above do not install OS packages or start services.

## Validation expectations

- For accounting and execution-control changes, preserve Decimal calculations, fresh-quote exit behavior, persisted loss limits, and replay protection.
- For model/data changes, test chronological separation, gap handling, provenance, and equivalence against a simple numerical reference where appropriate.
- For performance claims, identify the baseline, exact workload, environment, numerical tolerance, warmup, and repeated timing samples. Distinguish batch throughput from live latency.
- Keep raw datasets, environment files, logs, and generated ledgers out of commits. Commit small reproducible reports and data hashes where relevant.

Run `git diff --check` before submitting a pull request. Include the relevant test command and result. Report observed limitations and failed experiments; larger datasets or faster code do not by themselves demonstrate improved returns.

## Reporting problems

Include the release/commit, OS, Python and dependency versions, command, expected behavior, and a minimal reproducible example. For data errors, include the public source, requested UTC interval, and checksum where available. Use synthetic fixtures for tests when redistribution of raw source data is unsuitable.
