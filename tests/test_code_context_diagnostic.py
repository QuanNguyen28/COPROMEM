import runpy
from pathlib import Path

MODULE = runpy.run_path(
    str(
        Path(__file__).parents[1]
        / "research/scripts/diagnose_code_predicate_context.py"
    )
)


def test_public_store_diagnostic_is_name_specific_but_not_execution_proof():
    prefix = ["rows = []", "other = []", "if False:\n    rows = []", "print(rows)"]
    assert MODULE["assignment_indices"](prefix, "rows") == [0, 2]
    assert MODULE["assignment_indices"](prefix, "missing") == []
