#!/usr/bin/env bash
set -euo pipefail
ENV_DIR=/mnt/e/Project/AAMAS/reme-official-v3
CACHE_DIR=/mnt/e/Project/AAMAS/reme-pip-cache
TMP_DIR=/mnt/e/Project/AAMAS/reme-install-tmp
export TMPDIR="$TMP_DIR"
export PIP_CACHE_DIR="$CACHE_DIR"
export PIP_DISABLE_PIP_VERSION_CHECK=1

# AgentScope 1.0.20 imports SQLAlchemy's asyncio support; SQLAlchemy requires
# this optional runtime wheel for that path on CPython 3.12.
"$ENV_DIR/bin/python" -m pip install --cache-dir "$CACHE_DIR" 'greenlet==3.5.6'
"$ENV_DIR/bin/python" -m pip check
