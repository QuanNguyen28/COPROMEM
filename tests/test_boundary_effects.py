import copy
import runpy
from pathlib import Path

import pytest

from copromem.checkpoints import IntegrityError, digest

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "research/scripts/run_boundary_effects.py")
)


def test_only_selected_action_changes_and_original_objects_are_immutable():
    full = {
        "task_id": "fixture",
        "seed": 1,
        "actions": ["prefix", "original", "suffix"],
    }
    origin = {
        "prefix_request": {**full, "actions": ["prefix"]},
        "step": {"step": 1, "code": "original"},
    }
    saved = copy.deepcopy((origin, full))
    assert MODULE["replacement_request"](origin, full, "replacement")["actions"] == [
        "prefix",
        "replacement",
        "suffix",
    ]
    assert (origin, full) == saved
    with pytest.raises(IntegrityError):
        MODULE["replacement_request"](
            origin,
            {**full, "actions": ["different", "original", "suffix"]},
            "replacement",
        )


@pytest.mark.parametrize(
    "success,completed,unsupported,eligible,errors,expected",
    [
        (True, True, [], True, [1], True),
        (True, True, [], True, [1, 2], False),
        (False, True, [], True, [], False),
        (True, False, [], True, [], False),
        (True, True, ["object"], True, [], False),
        (True, True, [], False, [], False),
    ],
)
def test_effect_gate_retains_old_errors_but_rejects_introduced_errors_and_invalid_outcomes(
    success, completed, unsupported, eligible, errors, expected
):
    frame = {
        "completion_flag": completed,
        "harness_only_state": {"namespace": {"unsupported": unsupported}},
        "results": [
            {"output": "Execution failed." if i in errors else "ok"} for i in range(3)
        ],
    }
    assert (
        MODULE["passes"](frame, {"native_success": success}, (1,), eligible) is expected
    )


def test_manifest_deduplicates_only_same_origin_boundary_and_ast():
    candidates = {}
    for episode, index, ast_id, donor in [
        ("e", 1, "a", "d0"),
        ("e", 1, "a", "d1"),
        ("e", 2, "a", "d0"),
        ("f", 1, "a", "d0"),
    ]:
        row = {
            "origin_source": {"source_id": episode},
            "target_action_index": index,
            "proposal": {"program_ast_digest": ast_id},
            "donor": donor,
        }
        candidates[digest(row)] = row
    selected, controls = MODULE["manifest"](candidates)
    assert len(selected) == 3
    assert len(controls) == 2
    assert len(selected[0]["all_provenance_ids"]) == 2
    assert selected[0]["representative"] == min(selected[0]["all_provenance_ids"])
    assert controls[0]["action_index"] == 1
