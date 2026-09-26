#!/usr/bin/env bash
set -euo pipefail
ENV_DIR=/mnt/e/Project/AAMAS/reme-official-service-v3
OUT_DIR=/mnt/e/Project/AAMAS/COPROMEM/artifacts/research/official_reme_copromem_pilot/environment
mkdir -p "$OUT_DIR"
"$ENV_DIR/bin/python" -m pip check | tee "$OUT_DIR/reme-service-pip-check.txt"
"$ENV_DIR/bin/python" - <<'PY' | tee "$OUT_DIR/reme-service-imports.txt"
import importlib
import inspect
import pathlib
import sys

expected = pathlib.Path('/home/xiqhq/copromem-reme').resolve()
for name in ('flowllm', 'ray', 'reme_ai', 'reme_ai.service.task_memory_service'):
    mod = importlib.import_module(name)
    path = pathlib.Path(mod.__file__).resolve()
    print(f'{name}={path}')
    if name.startswith('reme_ai') and expected not in path.parents:
        raise RuntimeError(f'{name} does not resolve to pinned ReMe checkout')
if any('reme_paper_lifecycle' in item for item in sys.modules):
    raise RuntimeError('local ReMe adaptation imported')
service = importlib.import_module('reme_ai.service.task_memory_service')
print(f'TaskMemoryService={inspect.getsourcefile(service.TaskMemoryService)}')
PY
