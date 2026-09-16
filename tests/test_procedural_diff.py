import ast
from dataclasses import FrozenInstanceError

import pytest

from copromem.procedural_diff import (
    ast_identity,
    name_effects,
    parse_program,
    propose_transplants,
    reduce_transplants,
)

FAILED = """session = 'authored-session'
items = service.fetch(session)
legacy_sink = []
for item in items:
    legacy_sink.append(item)
print(legacy_sink)
"""
SUCCESS = """session = 'authored-session'
cursor = 0
amount = 7
items = []
while True:
    response = service.fetch(session, cursor, amount)
    if not response:
        break
    items.extend(response)
    cursor += 1
changed_sink = list(items)
print(changed_sink)
"""


def test_generic_binding_transplant_closes_dependencies_and_preserves_suffix():
    proposals, rejections = propose_transplants(FAILED, SUCCESS)
    assert len(proposals) == 1
    edit = proposals[0]
    assert edit.anchor == "items"
    assert edit.origin_span == (1, 2)
    assert edit.donor_span == (1, 5)
    assert edit.retained_donor_indices == (1, 2, 3, 4)
    assert rejections == [{"anchor": "session", "reason": "identical producer blocks"}]
    body = ast.parse(edit.program()).body
    original = ast.parse(FAILED).body
    assert [ast_identity(node) for node in body[5:]] == [
        ast_identity(node) for node in original[2:]
    ]
    assert "changed_sink" not in edit.program()
    assert "legacy_sink" in edit.program()


def test_operator_is_independent_of_binding_api_names_and_constants():
    failed = FAILED.replace("items", "records").replace(
        "service.fetch", "adapter.collect"
    )
    successful = (
        SUCCESS.replace("items", "records")
        .replace("service.fetch", "adapter.collect")
        .replace("amount = 7", "amount = 13")
    )
    proposals, _ = propose_transplants(failed, successful)
    assert len(proposals) == 1
    assert proposals[0].anchor == "records"
    assert "adapter.collect" in proposals[0].program()
    assert "amount = 13" in proposals[0].program()


def test_identical_program_has_no_proposal():
    proposals, rejected = propose_transplants(FAILED, FAILED)
    assert proposals == [] and rejected


def test_repeated_direct_binding_is_not_an_anchor():
    failed = "value = 1\nvalue = 2\nprint(value)\n"
    donor = "value = 3\nvalue = 4\nprint(value)\n"
    assert propose_transplants(failed, donor) == ([], [])


def test_top_level_deletion_does_not_rewrite_original_statements():
    edit = propose_transplants(FAILED, SUCCESS)[0][0]
    shortened = edit.without(2)
    assert shortened.retained_donor_indices == (1, 3, 4)
    assert "amount = 7" not in shortened.program()
    assert (
        shortened.record()["preserved_suffix_ast_digest"]
        == edit.record()["preserved_suffix_ast_digest"]
    )
    # Syntax validity is not dataflow or task validity; amount is now undefined.
    assert "amount" in shortened.program()
    with pytest.raises(ValueError):
        shortened.without(2)
    with pytest.raises(FrozenInstanceError):
        edit.anchor = "different"


def test_syntax_analysis_records_in_place_effect_and_augmented_read():
    reads, writes = name_effects(ast.parse("items.extend(response)").body[0])
    assert {"items", "response"} <= reads and "items" in writes
    reads, writes = name_effects(ast.parse("counter += 1").body[0])
    assert "counter" in reads & writes
    _, writes = name_effects(ast.parse("items[0] = 1").body[0])
    assert "items" in writes


@pytest.mark.parametrize(
    "program",
    ["def f():\n    return 1", "items = [x for x in source]", "f = lambda x: x"],
)
def test_unmodelled_lexical_scopes_fail_closed(program):
    with pytest.raises(ValueError, match="unsupported lexical scope"):
        parse_program(program)


def test_proposal_never_executes_programs_on_host():
    failed = "items = dangerous_function()\nprint(items)\n"
    donor = "items = another_dangerous_function()\nprint(items)\n"
    assert len(propose_transplants(failed, donor)[0]) == 1


def test_deletion_search_preserves_callback_gate_and_tests_final_neighbors():
    edit = propose_transplants(FAILED, SUCCESS)[0][0]
    calls = []

    def evaluate(variant):
        calls.append(variant.record()["program_ast_digest"])
        return {1, 3, 4} <= set(variant.retained_donor_indices)

    search = reduce_transplants([edit], evaluate, max_variants=12)
    assert len(calls) == len(set(calls)) == search["tested_variant_count"]
    retained = search["retained_edits"][0]
    assert retained["retained"]["retained_donor_indices"] == [1, 3, 4]
    assert retained["single_top_level_deletion_fixed_point"]
    assert not retained["global_minimality_claim"]
    assert search["search_complete"]


def test_variant_budget_is_hard_and_incomplete_is_not_minimality():
    edit = propose_transplants(FAILED, SUCCESS)[0][0]
    calls = []

    def evaluate(variant):
        calls.append(variant)
        return len(variant.retained_donor_indices) == 4

    search = reduce_transplants([edit], evaluate, max_variants=2)
    assert len(calls) == search["tested_variant_count"] == 2
    assert not search["search_complete"]
    assert not search["retained_edits"][0]["single_top_level_deletion_fixed_point"]
    assert search["decisions"][-1]["not_executed_due_to_budget"]


def test_failed_initial_proposal_is_not_promoted_or_reduced():
    edit = propose_transplants(FAILED, SUCCESS)[0][0]
    search = reduce_transplants([edit], lambda _: False, max_variants=12)
    assert search["tested_variant_count"] == 1
    assert search["retained_edits"] == []
    assert search["search_complete"]


@pytest.mark.parametrize("budget", [0, -1, True, 1.5])
def test_invalid_search_budgets_are_rejected(budget):
    with pytest.raises(ValueError):
        reduce_transplants([], lambda _: True, max_variants=budget)
