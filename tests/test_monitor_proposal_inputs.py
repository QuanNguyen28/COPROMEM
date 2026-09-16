import copy
import json
import runpy
from pathlib import Path

import pytest

from copromem.checkpoints import IntegrityError

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "research/scripts/monitor_proposal_inputs.py")
)


def public(program="print(existing)", names=("existing",)):
    return {
        "program": program,
        "envelope": {
            "version": MODULE["CHECK"]["PUBLIC"]["VERSION"],
            "bindings": [{"name": name, "present": True} for name in sorted(names)],
        },
    }


def corpus():
    cases = []
    for i in range(14):
        cases.append(
            {
                "origin_episode": "fixture-source",
                "action_index": 3,
                "checkpoint_digest": "checkpoint",
                "public_context_digest": "context",
                "public_input": public(f"answer = {i}\nprint(answer)", ("answer",)),
                "final_native_success_audit_only": i in (6, 13),
                "private_state": "must_not_reach_proposer",
            }
        )
    return cases


def test_literals_comments_and_provenance_do_not_reach_runtime():
    original = public(
        "# private-comment\nsecret = 'fixture-literal'\nprint(secret)", ("secret",)
    )
    saved = copy.deepcopy(original)
    result = MODULE["runtime_input"](original)
    assert result == {
        "program": "secret = '<string>'\nprint(secret)",
        "present_names": ["secret"],
    }
    assert original == saved
    assert set(result) == {"program", "present_names"}


def test_normalization_keeps_structure_and_numbers_but_does_not_execute():
    result = MODULE["runtime_input"](
        public("raise RuntimeError('literal')\nx = 17", ("x",))
    )
    assert "17" in result["program"] and "<string>" in result["program"]


def test_unknown_names_and_extra_hidden_fields_are_rejected():
    with pytest.raises(IntegrityError):
        MODULE["runtime_input"](public("print(unknown)", ()))
    with pytest.raises(ValueError):
        MODULE["runtime_input"]({**public(), "native_success": True})


@pytest.mark.parametrize(
    "field",
    ["origin_episode", "action_index", "checkpoint_digest", "public_context_digest"],
)
def test_pair_must_share_exact_source_context(field):
    cases = corpus()
    cases[6][field] = "changed"
    with pytest.raises(IntegrityError):
        MODULE["pair_examples"](cases, 0)


def test_pair_labels_and_exact_envelope_are_checked():
    cases = corpus()
    cases[6]["final_native_success_audit_only"] = 1
    with pytest.raises(IntegrityError):
        MODULE["pair_examples"](cases, 0)
    cases = corpus()
    cases[6]["public_input"]["envelope"]["bindings"][0]["present"] = False
    with pytest.raises(IntegrityError):
        MODULE["pair_examples"](cases, 0)


def test_success_only_request_contains_no_failed_example_or_provenance():
    cases = corpus()
    contrast = MODULE["request"](cases, 0, "contrast", 61)
    positive = MODULE["request"](cases, 0, "success_only", 61)
    examples = json.loads(positive["user"])["examples"]
    assert len(examples) == 1 and examples[0]["saved_continuation_success"] is True
    assert "answer = 10" not in positive["user"] and "answer = 6" in positive["user"]
    assert "must_not_reach_proposer" not in str(contrast)
    assert "checkpoint" not in str(contrast)
    assert contrast["system"] == positive["system"]
    assert {k: v for k, v in contrast.items() if k != "user"} == {
        k: v for k, v in positive.items() if k != "user"
    }


def test_fold_withholds_the_other_pair_and_uses_complete_fixed_sample():
    cases = corpus()
    payload = MODULE["request"](cases, 1, "contrast", 62)
    assert "answer = 12" in payload["user"] and "answer = 13" in payload["user"]
    assert "answer = 10" not in payload["user"] and "answer = 6" not in payload["user"]
    with pytest.raises(IntegrityError):
        MODULE["request"](cases[:-1], 1, "contrast", 62)
    with pytest.raises(ValueError):
        MODULE["request"](cases, 0, "selected_best", 61)


def test_constructed_byte_literal_is_quarantined():
    with pytest.raises(TypeError):
        MODULE["runtime_input"](public("data = b'not-forwarded'", ("data",)))
