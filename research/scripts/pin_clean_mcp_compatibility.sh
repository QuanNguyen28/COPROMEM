#!/usr/bin/env bash
set -euo pipefail
ENV_DIR=/mnt/e/Project/AAMAS/reme-official-v3
CACHE_DIR=/mnt/e/Project/AAMAS/reme-pip-cache
TMP_DIR=/mnt/e/Project/AAMAS/reme-install-tmp
export TMPDIR="$TMP_DIR"
export PIP_CACHE_DIR="$CACHE_DIR"
export PIP_DISABLE_PIP_VERSION_CHECK=1

"$ENV_DIR/bin/python" -m pip install --cache-dir "$CACHE_DIR" 'mcp==1.30.0'
"$ENV_DIR/bin/python" -m pip check
"$ENV_DIR/bin/python" - <<'PY'
from mcp.client.streamable_http import streamable_http_client
try:
    from mcp.client.streamable_http import streamablehttp_client
except ImportError as exc:
    raise SystemExit(f'legacy AgentScope symbol is unavailable: {exc}')
print('mcp-compatibility-symbols=present')
PY
