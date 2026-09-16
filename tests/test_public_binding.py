import ast
import copy
import inspect
import runpy
from pathlib import Path

import pytest

from copromem.procedural_diff import BlockTransplant, ast_identity

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "research/scripts/public_binding.py")
)
BIND = MODULE["bind_transplant"]
TARGET = "client_key = 'target-fixture'\nitems = apis.catalog.fetch(auth=client_key)\nprint(items, client_key)"
DONOR = "items = []\npage = 0\nwhile True:\n    batch = apis.catalog.fetch(auth=source_key, page=page)\n    if not batch:\n        break\n    items.extend(batch)\n    page += 1"


def edit(target=TARGET, donor=DONOR, origin_span=(0, 2), donor_span=(0, 3)):
    return BlockTransplant(
        target, donor, "items", origin_span, donor_span, tuple(range(*donor_span))
    )


def test_unique_api_binding_preserves_original_literal_and_consumer_ast():
    original = edit()
    saved = copy.deepcopy(original.record())
    result = BIND(original, [])
    assert result["status"] == "accepted_changed"
    assert result["mapping"] == {"source_key": "client_key"}
    assert result["preserved_setup_indices"] == [0]
    assert result["missing_inputs"] == result["missing_outputs"] == []
    assert "target-fixture" in result["program"]
    assert "source_key" not in result["program"]
    assert ast_identity(ast.parse(result["program"]).body[-1]) == ast_identity(
        ast.parse(TARGET).body[-1]
    )
    assert original.record() == saved


def test_unmodified_prefix_and_suffix_are_not_renamed():
    original = edit("keep = 'prefix'\n" + TARGET, origin_span=(1, 3))
    result = BIND(original, [])
    assert result["status"] == "accepted_changed"
    assert ast_identity(ast.parse(result["program"]).body[0]) == ast_identity(
        ast.parse(original.failed_program).body[0]
    )


@pytest.mark.parametrize(
    "extra",
    [
        "\nother = apis.catalog.fetch(auth=other_key)",
        "\nother = apis.catalog.fetch(auth='literal')",
    ],
)
def test_conflicting_or_nonidentifier_target_arguments_rejected(extra):
    result = BIND(edit(target=TARGET + extra), [])
    assert result["status"] == "rejected"
    assert any(
        row["reason"] == "ambiguous_or_nonidentifier_api_argument"
        for row in result["rejections"]
    )


@pytest.mark.parametrize(
    "donor",
    [
        DONOR.replace("apis.catalog", "apis.other"),
        DONOR.replace("auth=source_key", "different=source_key"),
    ],
)
def test_unmatched_api_or_argument_name_is_not_guessed(donor):
    result = BIND(edit(donor=donor), [])
    assert result["status"] == "rejected"
    assert result["missing_inputs"] == ["source_key"]


def test_donor_local_bindings_are_protected_from_renaming():
    target = ast.parse("items = apis.catalog.fetch(auth=client_key)").body
    donor = ast.parse(
        "source_key = 0\nitems = apis.catalog.fetch(auth=source_key)"
    ).body
    required, _ = MODULE["sequence_io"](donor)
    external = required - MODULE["bound"](donor) - MODULE["BUILTINS"]
    assert MODULE["infer_mapping"](target, donor, external) == ({}, [])


def test_mapping_cannot_capture_a_donor_loop_local():
    donor = DONOR.replace("page", "client_key")
    result = BIND(edit(donor=donor), [])
    assert result["status"] == "rejected"
    assert any(
        row["reason"] == "mapping_would_capture_donor_local"
        for row in result["rejections"]
    )


def test_output_loss_is_rejected_not_filled_with_empty_collection():
    candidate = BlockTransplant(
        "records = []\ncursor = 0\nprint(records)",
        "pages = []\ncursor = 0",
        "cursor",
        (0, 2),
        (0, 2),
        (0, 1),
    )
    result = BIND(candidate, [])
    assert result["status"] == "rejected"
    assert result["missing_outputs"] == ["records"]
    assert result["preserved_setup_indices"] == []


def test_nonliteral_target_setup_is_rejected_even_if_old_name_exists():
    result = BIND(
        edit(target=TARGET.replace("'target-fixture'", "acquire()")),
        ["client_key = 'old'"],
    )
    assert result["status"] == "rejected"
    assert any(
        row["reason"] == "mapped_target_setup_not_unique_literal_assignment"
        for row in result["rejections"]
    )


def test_public_prefix_binding_is_used_without_hidden_state():
    candidate = edit(
        target="items = apis.catalog.fetch(auth=client_key)\nprint(items)",
        origin_span=(0, 1),
    )
    assert (
        BIND(candidate, ["client_key = 'prefix-fixture'"])["status"]
        == "accepted_changed"
    )
    assert (
        BIND(candidate, ["if condition:\n    client_key = 'conditional'"])["status"]
        == "rejected"
    )
    assert list(inspect.signature(BIND).parameters) == ["edit", "public_prefix"]
    with pytest.raises(TypeError):
        BIND(candidate, [{"code": "client_key = 1", "native_success": True}])


def test_uncertain_conditional_donor_binding_is_not_treated_as_external_rename():
    candidate = edit(
        donor="if maybe:\n    source_key = 'local'\nitems = apis.catalog.fetch(auth=source_key)",
        donor_span=(0, 2),
    )
    result = BIND(candidate, [])
    assert result["status"] == "rejected"
    assert "source_key" not in result["mapping"]


def test_unsupported_prefix_scope_is_retained_as_rejection():
    result = BIND(edit(), ["def helper():\n    return 1"])
    assert result["status"] == "rejected"
    assert any(
        row["reason"] == "unsupported_or_invalid_binding_syntax"
        for row in result["rejections"]
    )


def test_arbitrary_variable_and_api_names_work_without_task_tables():
    candidate = edit(
        TARGET.replace("client_key", "receiver_input")
        .replace("catalog", "unseen")
        .replace("auth", "parameter"),
        DONOR.replace("source_key", "other_input")
        .replace("catalog", "unseen")
        .replace("auth", "parameter"),
    )
    result = BIND(candidate, [])
    assert result["mapping"] == {"other_input": "receiver_input"}
    assert result["status"] == "accepted_changed"


def test_assignment_reads_its_old_value_and_zero_iteration_loop_definitions_are_uncertain():
    required, defined = MODULE["sequence_io"](
        ast.parse("x = x + 1\nfor item in source:\n    loop_value = item").body
    )
    assert "x" in required
    assert "loop_value" not in defined


def test_unknown_keyword_expansion_prevents_unique_argument_claim():
    result = BIND(edit(target=TARGET + "\nother = apis.catalog.fetch(**unknown)"), [])
    assert result["status"] == "rejected"
    assert any(
        row["reason"] == "ambiguous_or_nonidentifier_api_argument"
        for row in result["rejections"]
    )
