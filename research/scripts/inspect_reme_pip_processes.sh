#!/usr/bin/env bash
set -euo pipefail
ps -eo pid=,ppid=,etime=,stat=,args= | grep -E '[p]ip|[r]eme-official-(v3|service-v3|agentscope-v3)' || true
pid=$(pgrep -f '/mnt/e/Project/AAMAS/reme-official-(service|agentscope)-v3/bin/python -m pip install' | head -1 || true)
if [[ -n "$pid" && -r "/proc/$pid/stat" ]]; then
  ticks_before=$(awk '{print $14 + $15}' "/proc/$pid/stat")
  files_before=$(find /mnt/e/Project/AAMAS/reme-install-tmp -type f 2>/dev/null | wc -l)
  sleep 10
  ticks_after=$(awk '{print $14 + $15}' "/proc/$pid/stat")
  files_after=$(find /mnt/e/Project/AAMAS/reme-install-tmp -type f 2>/dev/null | wc -l)
  printf 'installer_pid=%s cpu_ticks=%s->%s temp_files=%s->%s\n' "$pid" "$ticks_before" "$ticks_after" "$files_before" "$files_after"
fi
