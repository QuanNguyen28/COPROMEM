#!/usr/bin/env bash
set -euo pipefail

ENV_DIR=/mnt/e/Project/AAMAS/reme-official-v3
SOURCE_DIR=/home/xiqhq/copromem-reme
OUT_DIR=/mnt/e/Project/AAMAS/COPROMEM/artifacts/research/reme_copromem_comparison/official_upstream_scaled_fidelity/verification
mkdir -p "$OUT_DIR"

"$ENV_DIR/bin/python" - <<'PY' | tee "$OUT_DIR/official-reme-imports.txt"
import importlib
import inspect
import pathlib
import sys

expected = pathlib.Path('/home/xiqhq/copromem-reme').resolve()
for name in ('agentscope', 'flowllm', 'ray', 'reme_ai', 'reme_ai.service.task_memory_service'):
    module = importlib.import_module(name)
    path = pathlib.Path(module.__file__).resolve()
    print(f'{name}={path}')
    if name.startswith('reme_ai') and expected not in path.parents:
        raise RuntimeError(f'{name} did not resolve from pinned checkout: {path}')

for forbidden in ('reme_paper_lifecycle', 'copromem.reme_paper_lifecycle'):
    if forbidden in sys.modules:
        raise RuntimeError(f'forbidden local adaptation already imported: {forbidden}')
    if importlib.util.find_spec(forbidden) is not None:
        print(f'forbidden-local-module-visible={forbidden}')

service = importlib.import_module('reme_ai.service.task_memory_service')
for symbol in ('TaskMemoryService',):
    obj = getattr(service, symbol)
    print(f'{symbol}_source={inspect.getsourcefile(obj)}')
PY

"$ENV_DIR/bin/python" -m pip check | tee "$OUT_DIR/pip-check.txt"
