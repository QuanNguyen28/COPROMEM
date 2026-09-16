import importlib.util
import runpy
import sys
from pathlib import Path

import pytest

CONTAINERS = Path(__file__).parents[1] / "research/containers/appworld"


def test_explicit_wrapper_expands_only_its_imported_worker(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "copromem_worker_base", CONTAINERS / "worker.py"
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "copromem_worker_base", module)
    spec.loader.exec_module(module)
    assert module.MAX_ACTIONS == 50
    runpy.run_path(str(CONTAINERS / "worker_long_source.py"))
    assert module.MAX_ACTIONS == 100
    request = {"task_id": "27e1026_1", "seed": 100, "actions": ["pass"] * 100}
    assert module.checked_request(request) == request
    with pytest.raises(ValueError, match="bounded action list"):
        module.checked_request({**request, "actions": ["pass"] * 101})
    untouched = runpy.run_path(str(CONTAINERS / "worker.py"))
    assert untouched["MAX_ACTIONS"] == 50
    with pytest.raises(ValueError, match="bounded action list"):
        untouched["checked_request"](request)
