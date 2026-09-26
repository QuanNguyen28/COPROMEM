#!/usr/bin/env python3
"""Zero-model boot verifier for the pinned official ReMe application."""
from __future__ import annotations

import inspect
import os
import pathlib
import sys

for name in ("OPENROUTER_API_KEY", "DEEPSEEK_API_KEY", "HIVE_API_KEY", "FLOW_LLM_API_KEY", "FLOW_EMBEDDING_API_KEY"):
    os.environ.pop(name, None)

SOURCE = pathlib.Path("/home/xiqhq/copromem-reme").resolve()

from reme_ai.main import ReMeApp  # noqa: E402
from reme_ai.service.task_memory_service import TaskMemoryService  # noqa: E402

for cls in (ReMeApp, TaskMemoryService):
    path = pathlib.Path(inspect.getsourcefile(cls)).resolve()
    if SOURCE not in path.parents:
        raise RuntimeError(f"{cls.__name__} is not imported from pinned checkout: {path}")
    print(f"{cls.__name__}={path}")

if any("reme_paper_lifecycle" in module for module in sys.modules):
    raise RuntimeError("local ReMe adaptation imported")

# Construction parses official flows and registers the upstream components but
# does not start a service or execute any model/embedding operation.
app = ReMeApp("vector_store.default.backend=memory")
print(f"application_type={type(app).__module__}.{type(app).__qualname__}")
print("model_calls=0")
print("local_reme_adapter=absent")
