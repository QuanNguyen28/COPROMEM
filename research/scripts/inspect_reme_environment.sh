#!/usr/bin/env bash
set -euo pipefail
for d in /home/xiqhq/reme-v3 /home/xiqhq/ReMe /mnt/e/Project/AAMAS/ReMe /mnt/e/Project/AAMAS/reme-env; do
  if [ -e "$d" ]; then
    printf '%s\n' "$d"
  fi
done
find /home/xiqhq -maxdepth 3 -type d -name .git -printf '%h\n' 2>/dev/null | grep -i reme || true
df -h / /mnt/e
