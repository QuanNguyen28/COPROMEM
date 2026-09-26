#!/usr/bin/env bash
set -euo pipefail

ENV_DIR=/mnt/e/Project/AAMAS/reme-official-agentscope-v3
CACHE_DIR=/mnt/e/Project/AAMAS/reme-pip-cache
TMP_DIR=/mnt/e/Project/AAMAS/reme-install-tmp
OUT_DIR=/mnt/e/Project/AAMAS/COPROMEM/artifacts/research/reme_copromem_comparison/official_upstream_scaled_fidelity/environment
mkdir -p "$CACHE_DIR" "$TMP_DIR" "$OUT_DIR"
export TMPDIR="$TMP_DIR"
export PIP_CACHE_DIR="$CACHE_DIR"
export PIP_DISABLE_PIP_VERSION_CHECK=1

if [[ ! -x "$ENV_DIR/bin/python" ]]; then
  python3.12 -m venv "$ENV_DIR"
fi

# AgentScope 1.0.20 uses the MCP 1.x spelling streamablehttp_client.
# tqdm is explicitly declared by the pinned ReMe checkout (pyproject.toml) and
# is imported unconditionally by AgentScope's evaluation package at import
# time. Keep it in this legacy-MCP process rather than mixing MCP families.
"$ENV_DIR/bin/python" -m pip install --cache-dir "$CACHE_DIR" \
  'agentscope==1.0.20' 'mcp==1.30.0' 'greenlet==3.5.6' 'tqdm>=4.67.1'
"$ENV_DIR/bin/python" -m pip check
"$ENV_DIR/bin/python" -m pip freeze --all | LC_ALL=C sort > "$OUT_DIR/agentscope-pip-freeze.txt"
