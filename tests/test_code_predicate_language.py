import ast
import json
import runpy
from collections import Counter
from pathlib import Path

import pytest

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "research/scripts/code_predicate_language.py")
)


def clause(feature="node:Assign", operator="ge", threshold=1):
    return {
        "version": MODULE["VERSION"],
        "feature": feature,
        "operator": operator,
        "threshold": threshold,
    }


def test_all_node_and_edge_kinds_are_counted_without_domain_allowlist():
    source = "import arbitrary\ndef f(q):\n    try:\n        return [x*2 for x in q if x]\n    except TypeError:\n        raise\n"
    expected = Counter()

    def traverse(node):
        expected["node:" + type(node).__name__] += 1
        for field in node._fields:
            value = getattr(node, field)
            children = value if isinstance(value, list) else [value]
            for child in children:
                if isinstance(child, ast.AST):
                    expected[
                        f"edge:{type(node).__name__}:{field}:{type(child).__name__}"
                    ] += 1
                    traverse(child)

    traverse(ast.parse(source))
    assert MODULE["features"](source) == dict(expected)
    for feature in expected:
        MODULE["validate_clause"](clause(feature))


def test_name_api_literal_formatting_and_comment_invariance():
    first = "value = apis.first.fetch(key=secret, limit=3)\nprint('old')"
    second = "# comment\nrenamed=apis.other.entirelynew(arg=renamed_secret, size=999)\nprint(12345)"
    assert MODULE["features"](first) == MODULE["features"](second)
    assert MODULE["ast_identity"](first) != MODULE["ast_identity"](second)
    assert "secret" not in json.dumps(MODULE["features"](first))


def test_enum_is_complete_and_thresholds_are_observed_not_fixed():
    examples = [
        {"program": "pass", "label": False},
        {"program": "x=1\ny=2", "label": True},
        {"program": "a=3\nb=4\nc=5", "label": True},
    ]
    learned = MODULE["learn"](examples)
    vectors = learned["vectors"]
    expected = set()
    for feature in set().union(*(set(v) for v in vectors)):
        for count in {v.get(feature, 0) for v in vectors}:
            for op in ("ge", "le"):
                expected.add((feature, op, count))
    actual = {
        (r["clause"]["feature"], r["clause"]["operator"], r["clause"]["threshold"])
        for r in learned["enumeration"]
    }
    assert actual == expected
    assert len(actual) == len(learned["enumeration"])
    assert clause(threshold=2) in learned["accepted_clauses"]
    for row in learned["enumeration"]:
        direct = [
            MODULE["classify"](row["clause"], e["program"])["accepted"]
            for e in examples
        ]
        assert row["predictions"] == direct
        assert (row["status"] == "accepted") == (
            direct == [e["label"] for e in examples]
        )


def test_identical_code_opposite_labels_gives_empty_version_space():
    learned = MODULE["learn"](
        [{"program": "x=1", "label": True}, {"program": "x=1", "label": False}]
    )
    assert learned["enumeration"]
    assert learned["accepted_clauses"] == []
    assert all(row["disagreement_indices"] for row in learned["enumeration"])


def test_reversing_labels_changes_selected_predicates():
    examples = [{"program": "pass", "label": False}, {"program": "x=1", "label": True}]
    initial = MODULE["learn"](examples)["accepted_clauses"]
    opposite = MODULE["learn"]([{**e, "label": not e["label"]} for e in examples])[
        "accepted_clauses"
    ]
    assert initial and opposite
    assert not any(c in opposite for c in initial)


@pytest.mark.parametrize(
    "operator,threshold,expected",
    [("ge", 1, True), ("ge", 2, False), ("le", 1, True), ("le", 0, False)],
)
def test_comparison_boundaries_and_json_roundtrip(operator, threshold, expected):
    c = clause(operator=operator, threshold=threshold)
    assert MODULE["classify"](json.loads(json.dumps(c)), "x=1") == {
        "accepted": expected,
        "error": None,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"operator": "eval"},
        {"threshold": True},
        {"threshold": -1},
        {"threshold": 1.0},
        {"feature": "node:Spotify"},
        {"feature": "edge:Assign:missing:Name"},
        {"scope": "hidden"},
        {"version": "unrecognized"},
    ],
)
def test_invalid_clause_abstains(changes):
    assert MODULE["classify"]({**clause(), **changes}, "x=1")["accepted"] is None


@pytest.mark.parametrize("value", [None, "for", "x=\x00"])
def test_malformed_program_never_accepts(value):
    assert MODULE["classify"](clause(), value)["accepted"] is None


def test_source_is_parsed_without_execution(tmp_path):
    target = tmp_path / "must_not_exist"
    source = f"__import__('pathlib').Path({str(target)!r}).write_text('executed')"
    assert MODULE["classify"](clause("node:Call"), source)["accepted"] is True
    assert not target.exists()


@pytest.mark.parametrize(
    "examples",
    [
        [],
        [{"program": "pass", "label": 1}],
        [{"program": "pass", "label": True, "task_id": "leak"}],
        [{"program": 9, "label": True}],
        [{"program": "pass"}],
    ],
)
def test_learner_rejects_non_public_schema(examples):
    with pytest.raises(ValueError):
        MODULE["learn"](examples)


def test_confusion_keeps_abstentions_and_checks_denominator():
    assert MODULE["confusion"](
        [True, True, False, False, None], [True, False, False, True, True]
    ) == {
        "examples": 5,
        "true_accept": 1,
        "false_accept": 1,
        "true_reject": 1,
        "false_reject": 1,
        "abstentions": 1,
    }
    with pytest.raises(ValueError):
        MODULE["confusion"]([True], [])
    with pytest.raises(ValueError):
        MODULE["confusion"]([1], [True])
