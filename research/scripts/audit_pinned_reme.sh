#!/usr/bin/env bash
set -euo pipefail
repo=/home/xiqhq/copromem-reme
cd "$repo"
echo "remote=$(git remote get-url origin)"
echo "head=$(git rev-parse HEAD)"
echo "status=$(git status --porcelain | wc -l)"
echo "tree=$(git rev-parse HEAD^{tree})"
echo "tracked_content_sha256=$(git ls-files -z | sort -z | xargs -0 sha256sum | sha256sum | awk '{print $1}')"
echo appworld_files
find benchmark/appworld -maxdepth 2 -type f -printf '%P\n' | sort
echo manifests
find . -maxdepth 3 \( -iname 'requirements*.txt' -o -iname 'pyproject.toml' -o -iname 'setup.py' -o -iname 'Dockerfile*' -o -iname '*.yml' \) -print | sort
