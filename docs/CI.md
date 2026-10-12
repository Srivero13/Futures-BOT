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
older runs for the same ref. The job has a 15-minute limit.

Actions are pinned to verified commit SHAs. The token has read-only repository
content permission, checkout does not persist credentials, and no exchange keys,
live credentials or GPU are requested. Dependency installation and artifact
upload require network access; offline refers to the bot diagnostics and unit
tests, not the entire GitHub runner. Fixtures exercise download and connection
paths with mocks; their progress logs are not new market research results.

The current CPU environment runs 393 tests with two optional skips: Numba and
PyTorch are not installed by `requirements.txt`. The count can change with later
commits. GPU execution, actual broker connectivity, strategy profitability and
unattended operation are not certified by a passing check. No bots, training jobs
or market collectors are launched by this workflow.

Local equivalent:

```bash
python -m pip install -r requirements.txt
python doctor.py
python -m unittest discover -s tests -v
```

The full suite passed locally and on the operator's Ubuntu PC before this workflow
was added. The first GitHub-hosted run must be inspected separately; local success
does not establish that GitHub runner setup and artifact permissions succeeded.
