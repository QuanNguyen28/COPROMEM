#!/usr/bin/env bash
set -euo pipefail

ENV_DIR=/mnt/e/Project/AAMAS/reme-official-service-v3
SOURCE_DIR=/home/xiqhq/copromem-reme
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

# The official ReMe service uses FlowLLM/FastMCP.  It deliberately omits
# AgentScope, which is isolated in a separate MCP-1-compatible process.
"$ENV_DIR/bin/python" -m pip install --cache-dir "$CACHE_DIR" \
  'flowllm[reme]==0.2.0.10' 'ray==2.58.0' -e "$SOURCE_DIR"
"$ENV_DIR/bin/python" -m pip check
"$ENV_DIR/bin/python" -m pip freeze --all | LC_ALL=C sort > "$OUT_DIR/reme-service-pip-freeze.txt"
