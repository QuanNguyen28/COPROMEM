#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 2 ]]; then
  echo "usage: $0 PORT RUN_DIR" >&2
  exit 64
fi
export PYTHONPATH=/mnt/e/Project/AAMAS/COPROMEM
export OFFICIAL_REME_PORT="$1"
export OFFICIAL_REME_RUN_DIR="$2"
export OFFICIAL_REME_PROGRESS=/mnt/e/Project/AAMAS/COPROMEM/artifacts/research/official_reme_copromem_pilot/progress.jsonl
exec /mnt/e/Project/AAMAS/reme-official-service-v3/bin/python \
  /mnt/e/Project/AAMAS/COPROMEM/research/official_pilot/reme_service.py
