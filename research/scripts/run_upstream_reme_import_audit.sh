#!/usr/bin/env bash
# Run from WSL.  Persists the unusually slow first AgentScope import result so
# an interactive timeout cannot turn an import audit into an ambiguous failure.
set -u

ROOT=/mnt/e/Project/AAMAS/COPROMEM
PYTHON=/mnt/e/Project/AAMAS/reme-upstream-fixed-dynamic/bin/python
OUT="$ROOT/artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v1/upstream_import_audit"
mkdir -p "$OUT"

if [ "${1:-run}" = "launch" ]; then
  rm -f "$OUT/exit-status"
  nohup "$0" run >"$OUT/launcher.log" 2>&1 &
  printf '%s\n' "$!" >"$OUT/pid"
  exit 0
fi

PYTHONPATH=/home/xiqhq/copromem-reme "$PYTHON" \
  "$ROOT/research/scripts/verify_upstream_reme_imports.py" \
  >"$OUT/stdout.log" 2>"$OUT/stderr.log"
status=$?
printf '%s\n' "$status" >"$OUT/exit-status"
exit "$status"
