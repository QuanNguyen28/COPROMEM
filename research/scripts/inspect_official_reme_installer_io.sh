#!/usr/bin/env bash
set -euo pipefail
pid=$(pgrep -f '/mnt/e/Project/AAMAS/reme-official-(service|agentscope)-v3/bin/python -m pip install' | head -1 || true)
if [[ -z "$pid" ]]; then
  printf 'installer-not-running\n'
  exit 0
fi
if [[ ! -d "/proc/$pid" ]]; then
  printf 'installer-not-running\n'
  exit 0
fi
printf 'cwd='
readlink "/proc/$pid/cwd"
printf 'open regular files:\n'
for fd in /proc/"$pid"/fd/*; do
  target=$(readlink "$fd" 2>/dev/null || true)
  case "$target" in
    /mnt/e/*|/home/xiqhq/*|/tmp/*) printf '%s %s\n' "${fd##*/}" "$target" ;;
  esac
done
printf 'socket count='
find /proc/"$pid"/fd -type l -lname 'socket:*' 2>/dev/null | wc -l
