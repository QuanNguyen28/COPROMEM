#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="/home/xiqhq/copromem-appworld/venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="/mnt/e/Project/AAMAS/reme-upstream-fixed-dynamic/bin/python"
fi
cd "$ROOT"
PYTHONPATH=src "$PYTHON" -m pytest -q \
  tests/appworld/test_execution_evidence.py \
  tests/reme_copromem/test_contrastive_v6_integration_fixture.py
