#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"
exec env COPROMEM_ROOT="$root" PYTHONPATH="$root/src:$root" \
  "${COPROMEM_REME_PYTHON:-/mnt/e/Project/AAMAS/reme-upstream-fixed-dynamic/bin/python}" scripts/reme_copromem/run_fixed_dynamic.py
