# Automated offline regression checks

`.github/workflows/offline-tests.yml` runs on pushes to `develop`, `main` and
`master`, on pull requests, and through manual workflow dispatch. It uses Ubuntu
24.04 and Python 3.12 with the project's pinned CPU requirements. GitHub Actions
must be enabled for the repository; branch protection is not configured by this
workflow. A red check reports failure but does not itself prevent a push or merge.

The workflow runs `doctor.py` and the entire unittest suite. Tests still execute
if doctor fails after dependencies install successfully. Shell `pipefail` ensures
that saving logs through `tee` cannot hide a failing process. Diagnostic logs are
retained as an artifact for 14 days, including when a test fails. New runs cancel
older runs for the same ref. The base job has a 15-minute limit; the optional dependency job has a 20-minute limit.

Actions are pinned to verified commit SHAs. The token has read-only repository
content permission, checkout does not persist credentials, and no exchange keys,
live credentials or GPU are requested. Dependency installation and artifact
upload require network access; offline refers to the bot diagnostics and unit
tests, not the entire GitHub runner. Fixtures exercise download and connection
paths with mocks; their progress logs are not new market research results.

The base CPU environment runs 393 tests with two optional skips: Numba and
PyTorch are not installed by `requirements.txt`. A separate `optional-cpu-tests`
job installs `requirements-fast.txt` (Numba 0.63.1) and PyTorch 2.7.1 from its CPU
wheel index, then runs the full suite. It explicitly imports both dependencies,
checks package compatibility with `pip check`, and fails on any skipped test or
an empty suite. This exercises compiled forecast equivalence and synthetic MLP
signal recovery. The test count can change with later commits.

The optional job uses CPU execution only. It does not test CUDA drivers, GPU
kernels or GPU performance. Its PyTorch version matches the documented 2.7.1 GPU
research environment, but uses a different wheel. Do not install the CI CPU wheel
into an existing GPU environment. Both jobs run independently; neither silently
falls back when an optional dependency fails. GPU execution, actual broker connectivity, strategy profitability and
unattended operation are not certified by a passing check. No live bots, market-data training runs
or market collectors are launched. The optional test trains a small synthetic MLP.

Local equivalent:

```bash
python -m pip install -r requirements.txt
python doctor.py
python -m unittest discover -s tests -v
```

The initial base workflow completed successfully on GitHub Actions. Each new
workflow revision still needs its own hosted result; local success alone does
not establish that runner setup and artifact permissions succeeded.
