#!/usr/bin/env bash
set -euo pipefail
env=/mnt/e/Project/AAMAS/reme-env
cache=/mnt/e/Project/AAMAS/reme-pip-cache
temp=/mnt/e/Project/AAMAS/reme-install-tmp/mcp-audit
mkdir -p "$cache" "$temp"
"$env/bin/python" -m pip install --cache-dir "$cache" --find-links "$temp" mcp==1.30.0 greenlet
"$env/bin/python" -m pip check
"$env/bin/python" -m pip show mcp agentscope
sha256sum "$temp"/mcp-1.30.0-*.whl
