import copy
import runpy
from pathlib import Path

import pytest

from copromem.checkpoints import IntegrityError, digest

HERE = Path(__file__).parents[1] / "research/scripts"
SOURCE = runpy.run_path(str(HERE / "static_name_sources.py"))
RUN = runpy.run_path(str(HERE / "run_static_name_check.py"))


def frame():
    state = {
        "namespace": {
            "unsupported": {},
            "serializable": {"private_audit_only": "not a public input"},
        }
    }
    return {
        "status": "completed",
        "guards_enabled": True,
        "harness_only_state": state,
        "state_digest": digest(state),
        "task_id": "fixture",
        "request_id": "prefix",
        "native_version": "fixture",
        "initial_database_files": {},
        "public_instruction": "task",
        "results": [],
        "completion_flag": False,
    }


def test_context_binding_exports_only_parsed_public_presence():
    before = frame()
    envelope = SOURCE["bind_context"](
        before,
        copy.deepcopy(before),
        "planner",
        "planner",
        'COPROMEM_PRESENCE={"name":"x","present":false}',
        ["x"],
    )
    assert envelope["bindings"] == [{"name": "x", "present": False}]
    assert "private_audit_only" not in str(envelope)


@pytest.mark.parametrize("changed", ["planner", "state", "prefix"])
def test_different_planner_state_or_prefix_cannot_supply_context(changed):
    first, second, checkpoint = frame(), frame(), "planner"
    if changed == "planner":
        checkpoint = "other"
    elif changed == "state":
        second["harness_only_state"]["namespace"]["serializable"] = {}
        second["state_digest"] = digest(second["harness_only_state"])
    else:
        second["request_id"] = "different"
    with pytest.raises(IntegrityError):
        SOURCE["bind_context"](
            first,
            second,
            "planner",
            checkpoint,
            'COPROMEM_PRESENCE={"name":"x","present":false}',
            ["x"],
        )


def fixture_results():
    cases = [
        {
            "local_label": {
                "label": i == 0,
                "kind": "fixture",
                "name": "x" if i == 0 else None,
            }
        }
        for i in range(14)
    ]
    rows = [
        {
            "case_index": i,
            "context": context,
            "analysis": {"covered": True},
            "parsed": {
                "valid": True,
                "warning_names": ["x"] if i == 0 or (i == 1 and not context) else [],
            },
        }
        for i in range(14)
        for context in (False, True)
    ]
    return cases, rows


def test_primary_gate_requires_fewer_false_warnings_without_lost_detection():
    cases, rows = fixture_results()
    result = RUN["summarize"](cases, rows)
    assert result["decision"] == "KEEP" and result["false_warning_reduction"] == 1
    rows[1]["parsed"]["warning_names"] = []
    assert RUN["summarize"](cases, rows)["decision"] == "REVISE"


def test_unknown_context_is_quarantined_not_assumed_absent():
    cases, rows = fixture_results()
    rows[3]["analysis"]["covered"] = False
    result = RUN["summarize"](cases, rows)
    assert result["excluded_indices"] == [1] and result["cases"] == 14
    assert result["decision"] == "REVISE"


def test_missing_or_duplicate_checker_cells_fail_accounting():
    cases, rows = fixture_results()
    with pytest.raises(IntegrityError):
        RUN["summarize"](cases, rows[:-1])
    rows[-1] = copy.deepcopy(rows[0])
    with pytest.raises(IntegrityError):
        RUN["summarize"](cases, rows)
