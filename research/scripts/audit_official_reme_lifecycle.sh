#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR=/home/xiqhq/copromem-reme
cd "$SOURCE_DIR"

git remote get-url origin
git rev-parse HEAD
git status --porcelain
find benchmark/appworld -maxdepth 2 -type f -name '*.py' -print | LC_ALL=C sort
printf '\nLifecycle symbols:\n'
grep -RInE --include='*.py' \
  'retrieve_task_memory|summary_task_memory|update_memory_information|delete_memory|distill|retriev|prun|frequency|utility|reflect|dynamic' \
  benchmark reme_ai
