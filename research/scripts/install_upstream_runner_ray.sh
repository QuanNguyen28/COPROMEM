#!/usr/bin/env bash
set -euo pipefail
env=/home/xiqhq/copromem-appworld/venv
"$env/bin/python" -m pip install ray==2.58.0
"$env/bin/python" -m pip check
"$env/bin/python" -m pip show ray
