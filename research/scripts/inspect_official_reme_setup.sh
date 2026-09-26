#!/usr/bin/env bash
set -euo pipefail

printf 'C/root: '
df -h / | tail -1
printf 'E: '
df -h /mnt/e | tail -1

for path in \
  /mnt/e/Project/AAMAS/reme-official-v3 \
  /mnt/e/Project/AAMAS/reme-env \
  /home/xiqhq/copromem-reme; do
  if [[ -e "$path" ]]; then
    ls -ld "$path"
  else
    printf 'MISSING %s\n' "$path"
  fi
done

ps -eo pid=,args= | grep -E '[p]ip|[r]eme-official|[r]eme-env' || true
ps -o pid=,ppid=,etime=,stat=,pcpu=,pmem=,args= -p 404,436 2>/dev/null || true
pstree -ap 404 2>/dev/null || true
ps -o pid=,ppid=,etime=,stat=,pcpu=,pmem=,args= --ppid 404 2>/dev/null || true

if [[ -x /mnt/e/Project/AAMAS/reme-official-v3/bin/python ]]; then
  /mnt/e/Project/AAMAS/reme-official-v3/bin/python -m pip check
fi

du -sh /mnt/e/Project/AAMAS/reme-install-tmp /mnt/e/Project/AAMAS/reme-pip-cache 2>/dev/null || true
du -sh /mnt/e/Project/AAMAS/reme-official-v3 2>/dev/null || true
