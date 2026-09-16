import json
import runpy
from pathlib import Path

import pytest

M = runpy.run_path(
    str(Path(__file__).parents[1] / "research/scripts/teacher_repair_compat.py")
)
OBJECT = json.dumps(
    {"action_index": 1, "code": "print('literal {braces}')", "diagnosis": "fixture"}
)


def test_unique_object_extraction_preserves_exact_code_and_records_span():
    text = "Commentary Ω\n```json\n" + OBJECT + "\n```"
    parsed, proof = M["extract"](text, [1])
    assert parsed["code"] == "print('literal {braces}')"
    assert (
        text[proof["object_start_character"] : proof["object_end_character"]] == OBJECT
    )
    assert (
        text.encode()[
            proof["object_start_utf8_byte"] : proof["object_end_utf8_byte"]
        ].decode()
        == OBJECT
    )
    assert proof["code_modified"] is False


@pytest.mark.parametrize(
    "text",
    [
        "no object",
        OBJECT + OBJECT,
        '{"action_index":1,"action_index":1,"code":"print(1)","diagnosis":"x"}',
        '{"action_index":1,"code":"print(1)","diagnosis":"x"',
        '{"action_index":1,"code":"import os","diagnosis":"x"}',
    ],
)
def test_missing_ambiguous_duplicate_malformed_and_unsafe_cases_are_rejected(text):
    with pytest.raises(ValueError):
        M["extract"](text, [1])


def test_wrong_target_still_rejected_and_embedded_program_not_executed():
    with pytest.raises(ValueError):
        M["extract"](OBJECT, [2])
    text = json.dumps(
        {
            "action_index": 1,
            "code": "raise RuntimeError('not executed')",
            "diagnosis": "fixture",
        }
    )
    assert M["extract"](text, [1])[0]["status"] == "valid_proposal"
