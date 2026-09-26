#!/usr/bin/env bash
set -euo pipefail
ROOT=/mnt/e/Project/AAMAS/COPROMEM
OUT="$ROOT/artifacts/research/official_reme_copromem_pilot"
mkdir -p "$OUT"
nohup /mnt/e/Project/AAMAS/reme-official-service-v3/bin/python \
  "$ROOT/scripts/run_official_reme_copromem_pilot.py" \
  >>"$OUT/runner.stdout.log" 2>>"$OUT/runner.stderr.log" < /dev/null &
pid=$!
printf '%s\n' "$pid" > "$OUT/runner.pid"
echo "pid=$pid status=$OUT/runner-status.json progress=$OUT/progress.jsonl report=$OUT/FINAL_REPORT.md"
