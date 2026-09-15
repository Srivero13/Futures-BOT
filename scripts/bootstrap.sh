#!/usr/bin/env bash
set -euo pipefail
# Run inside the cloned repository on Ubuntu 24.04. Does not start a bot.
cd "$(dirname "$0")/.."
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip ca-certificates
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
printf '%s\n' 'Setup complete. Follow docs/OPERATIONS.md to observe public data.'
