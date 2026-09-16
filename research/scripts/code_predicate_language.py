"""Generic AST-count clauses: a bounded proposal language, not semantic verification."""

from __future__ import annotations

import ast
from collections import Counter

VERSION = "uniform-ast-node-and-field-edge-count-threshold-v1"
NODE_TYPES = {
    name: value
    for name, value in vars(ast).items()
    if isinstance(value, type) and issubclass(value, ast.AST)
}


def features(program: str) -> dict[str, int]:
    """Count all node classes and direct AST-field edges; never execute input."""
    if not isinstance(program, str):
        raise TypeError("program must be source text")
    tree = ast.parse(program)
    counts: Counter[str] = Counter()
    for node in ast.walk(tree):
        parent = type(node).__name__
        counts["node:" + parent] += 1
        for field, value in ast.iter_fields(node):
            children = value if isinstance(value, list) else [value]
            for child in children:
                if isinstance(child, ast.AST):
                    counts[f"edge:{parent}:{field}:{type(child).__name__}"] += 1
    return dict(sorted(counts.items()))


def ast_identity(program: str) -> str:
    """Normalized AST text; includes literal/name values, unlike feature vectors."""
    return ast.dump(ast.parse(program), include_attributes=False)


def validate_clause(clause: dict) -> None:
    if not isinstance(clause, dict) or set(clause) != {
        "version",
        "feature",
        "operator",
        "threshold",
    }:
        raise ValueError("invalid clause schema")
    if (
        clause["version"] != VERSION
        or clause["operator"] not in ("ge", "le")
        or type(clause["threshold"]) is not int
        or clause["threshold"] < 0
        or not isinstance(clause["feature"], str)
    ):
        raise ValueError("invalid clause language value")
    parts = clause["feature"].split(":")
    if len(parts) == 2 and parts[0] == "node" and parts[1] in NODE_TYPES:
        return
    if (
        len(parts) == 4
        and parts[0] == "edge"
        and parts[1] in NODE_TYPES
        and parts[2] in NODE_TYPES[parts[1]]._fields
        and parts[3] in NODE_TYPES
    ):
        return
    raise ValueError("feature is not an AST node or field-edge description")


def predict_counts(clause: dict, counts: dict[str, int]) -> bool:
    validate_clause(clause)
    value = counts.get(clause["feature"], 0)
    if type(value) is not int or value < 0:
        raise ValueError("feature count must be a nonnegative integer")
    if clause["operator"] == "ge":
        return value >= clause["threshold"]
    return value <= clause["threshold"]


def classify(clause: dict, program: str) -> dict:
    try:
        accepted = predict_counts(clause, features(program))
    except (SyntaxError, ValueError, TypeError, RecursionError):
        return {"accepted": None, "error": "invalid_or_unsupported_source_or_clause"}
    return {"accepted": accepted, "error": None}


def validate_examples(examples: list[dict]) -> None:
    if not isinstance(examples, list) or not examples:
        raise ValueError("nonempty public example list required")
    for example in examples:
        if (
            not isinstance(example, dict)
            or set(example) != {"program", "label"}
            or not isinstance(example["program"], str)
            or type(example["label"]) is not bool
        ):
            raise ValueError("example accepts only source text and binary label")


def learn(examples: list[dict]) -> dict:
    """Enumerate every observed threshold of every training feature, both ways."""
    validate_examples(examples)
    vectors = [features(example["program"]) for example in examples]
    names = sorted({name for vector in vectors for name in vector})
    rows = []
    for name in names:
        thresholds = sorted({vector.get(name, 0) for vector in vectors})
        for threshold in thresholds:
            for operator in ("ge", "le"):
                clause = {
                    "version": VERSION,
                    "feature": name,
                    "operator": operator,
                    "threshold": threshold,
                }
                predictions = [predict_counts(clause, vector) for vector in vectors]
                errors = [
                    i
                    for i, (prediction, example) in enumerate(
                        zip(predictions, examples)
                    )
                    if prediction != example["label"]
                ]
                rows.append(
                    {
                        "clause": clause,
                        "predictions": predictions,
                        "disagreement_indices": errors,
                        "status": "accepted" if not errors else "rejected",
                        "reason": None if not errors else "training_label_disagreement",
                    }
                )
    return {
        "version": VERSION,
        "vectors": vectors,
        "enumeration": rows,
        "accepted_clauses": [
            row["clause"] for row in rows if row["status"] == "accepted"
        ],
        "limitation": "Syntactic count classification of weak effect labels, not a sound semantic contract.",
    }


def confusion(predictions: list[bool | None], labels: list[bool]) -> dict:
    if len(predictions) != len(labels):
        raise ValueError("prediction denominator differs from label denominator")
    if any(type(label) is not bool for label in labels) or any(
        value is not None and type(value) is not bool for value in predictions
    ):
        raise ValueError("confusion inputs require binary values or abstentions")
    return {
        "examples": len(labels),
        "true_accept": sum(p is True and y for p, y in zip(predictions, labels)),
        "false_accept": sum(p is True and not y for p, y in zip(predictions, labels)),
        "true_reject": sum(p is False and not y for p, y in zip(predictions, labels)),
        "false_reject": sum(p is False and y for p, y in zip(predictions, labels)),
        "abstentions": sum(p is None for p in predictions),
    }
