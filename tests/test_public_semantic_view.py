import copy
import runpy
from pathlib import Path

import pytest

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "research/scripts/public_semantic_view.py")
)


def doc():
    return {
        "app_name": "example",
        "api_name": "fetch",
        "path": "/items",
        "method": "GET",
        "description": "Fetch items.",
        "parameters": [
            {
                "name": "access_token",
                "type": "string",
                "required": True,
                "default": None,
            }
        ],
        "response_schemas": {"success": [{"genre": "string", "artists": [{"id": 1}]}]},
        "canary_string": "not part of the projected public view",
    }


def public(program):
    tree = MODULE["ast"].parse(program)
    names = MODULE["CHECK"]["PUBLIC"]["selected_names"]([program])
    assert tree is not None
    return {
        "program": program,
        "envelope": {
            "version": MODULE["CHECK"]["PUBLIC"]["VERSION"],
            "bindings": [{"name": n, "present": n == "song_details"} for n in names],
        },
    }


def build(program, instruction="Use all classical songs."):
    return MODULE["build_view"](public(program), instruction, {"example.fetch": doc()})


def test_genre_information_is_preserved_and_authentication_literal_is_redacted():
    prefix = "access_token = 'fixture-auth-opaque-123'\nitems = apis.example.fetch(access_token=access_token)\n"
    good, checks = build(prefix + "selected = song_details['genre'] == 'classical'")
    other, _ = build(prefix + "selected = song_details['genre'] == 'different'")
    assert good != other
    assert "classical" in good["program"] and "'genre'" in good["program"]
    assert "fixture-auth-opaque-123" not in str(good)
    assert checks["credential_literal_occurrences_redacted"] == 1
    assert "<opaque-credential:0>" in good["program"]
    assert "canary_string" not in str(good)


def test_alias_and_inline_credential_literals_are_redacted_without_execution():
    view, checks = build(
        "auth = 'fixture-alias-123'\naccess_token = auth\nitems = apis.example.fetch(access_token=access_token)\nraise RuntimeError('not executed')"
    )
    assert "fixture-alias-123" not in view["program"]
    assert "not executed" in view["program"] and not checks["program_executed"]
    view, checks = build(
        "items = apis.example.fetch(access_token='fixture-inline-123')"
    )
    assert "fixture-inline-123" not in view["program"]
    assert checks["credential_literal_occurrences_redacted"] == 1


def test_same_credential_keeps_alias_equality_and_different_ones_stay_distinct():
    view, checks = build(
        "access_token='opaque-A'\nother_token='opaque-B'\nthird_token='opaque-A'"
    )
    assert checks["distinct_credential_values_redacted"] == 2
    assert view["program"].count("<opaque-credential:0>") == 2
    assert view["program"].count("<opaque-credential:1>") == 1


def test_inputs_are_immutable_and_native_labels_do_not_enter_view():
    original, docs = (
        public("selected = song_details['artists'][0]['id']"),
        {"example.fetch": doc()},
    )
    saved = copy.deepcopy((original, docs))
    view, _ = MODULE["build_view"](original, "All artists", docs)
    assert (original, docs) == saved
    assert set(view) == {
        "version",
        "program",
        "task_instruction",
        "public_presence",
        "api_docs",
    }
    with pytest.raises(ValueError):
        MODULE["build_view"]({**original, "native_success": True}, "All artists", docs)


@pytest.mark.parametrize(
    "program",
    [
        "access_token = 'same-value'\nselected = song_details['genre'] == 'same-value'",
        "access_token = 'base' + suffix",
        "access_token = b'encoded'",
        "access_token = 'opaque'\nselected = '<opaque-credential:0>'",
    ],
)
def test_ambiguous_or_unsupported_credential_cases_are_withheld(program):
    with pytest.raises(ValueError):
        build(program)


def test_credential_echo_in_task_metadata_is_not_forwarded():
    with pytest.raises(ValueError):
        build("access_token='fixture-auth-123'", "Use fixture-auth-123")


def test_missing_documentation_is_not_fabricated():
    with pytest.raises(ValueError):
        MODULE["build_view"](
            public("apis.example.fetch(access_token='opaque')"), "All items", {}
        )
