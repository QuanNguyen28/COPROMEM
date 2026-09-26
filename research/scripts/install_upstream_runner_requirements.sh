#!/usr/bin/env bash
set -euo pipefail
env=/home/xiqhq/copromem-appworld/venv
"$env/bin/python" -m pip install openai jinja2 loguru
"$env/bin/python" -m pip check
"$env/bin/python" -m pip show openai jinja2 loguru
