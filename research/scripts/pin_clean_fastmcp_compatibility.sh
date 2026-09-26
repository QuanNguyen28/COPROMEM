#!/usr/bin/env bash
set -euo pipefail
ENV_DIR=/mnt/e/Project/AAMAS/reme-official-v3
CACHE_DIR=/mnt/e/Project/AAMAS/reme-pip-cache
TMP_DIR=/mnt/e/Project/AAMAS/reme-install-tmp
export TMPDIR="$TMP_DIR"
export PIP_CACHE_DIR="$CACHE_DIR"
export PIP_DISABLE_PIP_VERSION_CHECK=1

# ReMe declares fastmcp>=2.14.1.  Version 2.14.1 is the lowest compliant
# release and its metadata accepts MCP 1.30.0, unlike the latest 4.x line.
"$ENV_DIR/bin/python" -m pip install --cache-dir "$CACHE_DIR" 'fastmcp==2.14.1' 'mcp==1.30.0'
"$ENV_DIR/bin/python" -m pip check
