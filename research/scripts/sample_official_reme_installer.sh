#!/usr/bin/env bash
set -euo pipefail

pid=404
if [[ ! -d "/proc/$pid" ]]; then
  printf 'installer-not-running\n'
  exit 0
fi

before=$(awk '{print $14 + $15}' "/proc/$pid/stat")
before_files=$(find /mnt/e/Project/AAMAS/reme-install-tmp -type f 2>/dev/null | wc -l)
sleep 10
after=$(awk '{print $14 + $15}' "/proc/$pid/stat")
after_files=$(find /mnt/e/Project/AAMAS/reme-install-tmp -type f 2>/dev/null | wc -l)
printf 'cpu_ticks_before=%s cpu_ticks_after=%s temp_files_before=%s temp_files_after=%s\n' \
  "$before" "$after" "$before_files" "$after_files"
