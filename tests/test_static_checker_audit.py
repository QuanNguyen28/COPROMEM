import runpy
from pathlib import Path

import pytest

from copromem.checkpoints import IntegrityError

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "research/scripts/audit_static_name_check.py")
)


@pytest.mark.parametrize(
    "field,value",
    [
        ("stdout", "different"),
        ("stderr", "warning"),
        ("exit_code", 2),
        ("stdin", "changed"),
        ("argv", ["another tool"]),
    ],
)
def test_checker_repeat_requires_full_raw_process_equality(field, value):
    process = {
        "stdout": "[]",
        "stderr": "",
        "exit_code": 0,
        "stdin": "pass",
        "argv": ["ruff"],
    }
    MODULE["same_process"](process, dict(process))
    with pytest.raises(IntegrityError):
        MODULE["same_process"](process, {**process, field: value})
