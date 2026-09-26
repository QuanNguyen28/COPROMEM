#!/usr/bin/env bash
set -euo pipefail
source /mnt/e/Project/AAMAS/reme-env/bin/activate
cd /home/xiqhq/copromem-reme
python - <<'PY'
import reme_ai
from reme_ai.main import ReMeApp
from reme_ai.service.task_memory_service import TaskMemoryService
print("reme_ai_file=" + reme_ai.__file__)
print("app_file=" + ReMeApp.__module__)
print("task_memory_service_file=" + TaskMemoryService.__module__)
PY
