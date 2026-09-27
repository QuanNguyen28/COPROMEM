#!/usr/bin/env bash
set -euo pipefail
cd /mnt/e/Project/AAMAS/COPROMEM
exec env PYTHONPATH=/mnt/e/Project/AAMAS/COPROMEM \
  /mnt/e/Project/AAMAS/reme-upstream-fixed-dynamic/bin/python scripts/run_fixed_dynamic_v4.py
