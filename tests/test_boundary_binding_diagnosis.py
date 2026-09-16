import runpy
from pathlib import Path

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "research/scripts/diagnose_boundary_bindings.py")
)


def test_name_diagnostic_uses_names_not_available_values():
    result = MODULE["possible_missing_names"](
        "rows = remote(input=donor_input)\nprint(rows)", {"remote"}
    )
    assert result == ["donor_input"]
    assert (
        MODULE["possible_missing_names"](
            "import math as calculation\nprint(calculation.sqrt(4))", set()
        )
        == []
    )


def test_name_diagnostic_is_explicitly_not_definite_assignment_proof():
    # A name syntactically stored in a never-taken branch is not flagged. This
    # limitation prevents describing the diagnostic as a sound executable guard.
    assert (
        MODULE["possible_missing_names"](
            "if False:\n    conditional = 1\nprint(conditional)", set()
        )
        == []
    )
