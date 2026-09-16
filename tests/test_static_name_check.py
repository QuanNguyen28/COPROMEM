import json
import runpy
from pathlib import Path

import pytest

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "research/scripts/static_name_check.py")
)


def public(program="print(existing, absent, unknown)"):
    return {
        "program": program,
        "envelope": {
            "version": MODULE["PUBLIC"]["VERSION"],
            "bindings": [
                {"name": "absent", "present": False},
                {"name": "existing", "present": True},
            ],
        },
    }


def test_context_stubs_are_analysis_only_and_absence_is_not_unknown():
    original = public()
    plain = MODULE["analysis_input"](original, context=False)
    context = MODULE["analysis_input"](original, context=True)
    assert plain["provided_names"] == ["apis"]
    assert context["provided_names"] == ["apis", "existing"]
    assert context["line_offset"] == 2 and context["absent_names"] == ["absent"]
    assert context["unknown_names"] == ["unknown"] and not context["covered"]
    assert context["source"] == "apis = None\nexisting = None\n" + original["program"]
    assert original == public()


def test_constructing_stubs_does_not_execute_source_or_raise_its_exception():
    text = "raise RuntimeError('must_not_execute')"
    assert MODULE["analysis_input"](public(text), context=True)["source"].endswith(text)


def test_checker_has_no_label_score_or_hidden_namespace_inputs():
    for field in ["label", "native_success", "namespace", "task_id"]:
        with pytest.raises(ValueError):
            MODULE["analysis_input"](
                {**public(), field: "must_not_enter"}, context=True
            )


@pytest.mark.parametrize(
    "output,expected,kind",
    [
        (
            "Execution failed.\nTraceback\nNameError: name 'absent' is not defined",
            True,
            "uncaught_missing_name",
        ),
        (
            "normal output\nNameError: name 'printed' is not defined",
            False,
            "no_uncaught_execution_error",
        ),
        ("Execution failed.\nNameError: custom message", None, "ambiguous_name_error"),
        (
            "Execution failed.\nTypeError: bad type",
            None,
            "other_or_ambiguous_execution_failure",
        ),
        ("done", False, "no_uncaught_execution_error"),
        ("", None, "missing_or_empty_public_output"),
        (None, None, "missing_or_empty_public_output"),
    ],
)
def test_local_name_error_label_never_uses_final_native_score(output, expected, kind):
    result = MODULE["local_label"](output)
    assert result["label"] is expected and result["kind"] == kind


def finding():
    return {
        "code": "F821",
        "location": {"row": 2, "column": 7},
        "end_location": {"row": 2, "column": 14},
        "filename": str(MODULE["ROOT"] / MODULE["FILENAME"]),
        "message": "Undefined name `missing`",
    }


def test_f821_mapping_removes_only_stub_line_offset():
    result = MODULE["parse_findings"](
        {"exit_code": 1, "stderr": "", "stdout": json.dumps([finding()])},
        {"source": "apis = None\nprint(missing)\n", "line_offset": 1},
    )
    assert result["valid"] and result["warning_names"] == ["missing"]
    assert result["findings"][0]["original_row"] == 1


@pytest.mark.parametrize(
    "change", ["exit", "stderr", "json", "rule", "offset", "file", "name", "column"]
)
def test_malformed_status_findings_and_source_locations_are_not_warnings(change):
    item = finding()
    submitted = {"source": "apis = None\nprint(missing)\n", "line_offset": 1}
    process = {"exit_code": 1, "stderr": "", "stdout": ""}
    if change == "exit":
        process["exit_code"] = 2
    elif change == "stderr":
        process["stderr"] = "unexpected warning"
    elif change == "rule":
        item["code"] = "F401"
    elif change == "offset":
        submitted["line_offset"] = 2
    elif change == "file":
        item["filename"] = "different.py"
    elif change == "name":
        item["message"] = "Undefined name `other`"
    elif change == "column":
        item["location"]["column"] = True
    process["stdout"] = "{" if change == "json" else json.dumps([item])
    assert not MODULE["parse_findings"](process, submitted)["valid"]


def test_exit_zero_and_one_have_different_meanings():
    submitted = {"source": "apis = None\npass", "line_offset": 1}
    assert MODULE["parse_findings"](
        {"exit_code": 0, "stdout": "[]", "stderr": ""}, submitted
    )["valid"]
    assert not MODULE["parse_findings"](
        {"exit_code": 1, "stdout": "[]", "stderr": ""}, submitted
    )["valid"]
