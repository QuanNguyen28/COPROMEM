#!/usr/bin/env bash
set -euo pipefail
env=/mnt/e/Project/AAMAS/reme-env
"$env/bin/python" -m pip install --cache-dir /mnt/e/Project/AAMAS/reme-pip-cache appworld==0.1.3.post1
"$env/bin/python" -m pip check
"$env/bin/python" -m pip show appworld
