"""Cycle-19 exhaustive weak-label predicate proposal and ambiguity diagnostic."""

from __future__ import annotations

import argparse
import json
import platform
import runpy
from collections import defaultdict
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, digest

HERE = Path(__file__).resolve().parent
LANG = runpy.run_path(str(HERE / "code_predicate_language.py"))
SOURCE = runpy.run_path(str(HERE / "code_predicate_sources.py"))


def overlap_key(row: dict) -> tuple:
    return row["origin_episode"], row["action_index"], digest(row["public"]["program"])


def conflicts(rows: list[dict], vectors: list[dict], field: str) -> list[dict]:
    groups = defaultdict(list)
    for index, (row, vector) in enumerate(zip(rows, vectors, strict=True)):
        if row["eligible"] and vector["error"] is None:
            groups[digest(vector[field])].append(index)
    return [
        {
            "identity": key,
            "indices": indices,
            "labels": [rows[i]["public"]["label"] for i in indices],
        }
        for key, indices in sorted(groups.items())
        if len({rows[i]["public"]["label"] for i in indices}) > 1
    ]


def run(store: RunStore, *, audit_only: bool = False) -> dict:
    root = HERE.parents[1]
    protocol = store.read("protocol", "preregistration")
    if protocol is None:
        if audit_only:
            raise IntegrityError("no frozen cycle-19 protocol to audit")
        paths = [
            *sorted((root / "src/copromem").glob("*.py")),
            *sorted(HERE.glob("*.py")),
            root / "research/045_CYCLE19_CODE_PREDICATE_IDENTIFIABILITY_PROTOCOL.md",
            root / "tests/test_code_predicate_language.py",
            root / "tests/test_code_predicate_sources.py",
        ]
        texts = {
            p.relative_to(root).as_posix(): p.read_text(encoding="utf-8") for p in paths
        }
        protocol = {
            "cycle": "cycle19-code-only-predicate-identifiability",
            "language": LANG["VERSION"],
            "source_reports": {
                name: value[2] for name, value in SOURCE["SOURCES"].items()
            },
            "source_snapshot": digest(texts),
            "python": platform.python_version(),
            "training_examples": 4,
            "diagnostic_cells": 48,
            "model_calls": 0,
            "native_executions": 0,
            "api_usd": 0,
        }
        store.bind_provenance({"protocol_digest": digest(protocol)})
        store.write("source_snapshots", digest(texts), texts)
        store.write("protocol", "preregistration", protocol)
    snapshot = store.read("source_snapshots", protocol["source_snapshot"])
    if (
        digest(snapshot) != protocol["source_snapshot"]
        or any(
            (root / path).read_text(encoding="utf-8") != value
            for path, value in snapshot.items()
        )
        or platform.python_version() != protocol["python"]
        or protocol["language"] != LANG["VERSION"]
        or protocol["source_reports"]
        != {name: value[2] for name, value in SOURCE["SOURCES"].items()}
    ):
        raise IntegrityError("frozen predicate language/source/environment changed")
    expected = defaultdict(set)
    for kind in (
        "source_audits",
        "examples",
        "public_examples",
        "construction",
        "clauses",
        "feature_vectors",
        "clause_diagnostics",
        "leave_pair_out",
        "reports",
    ):
        expected[kind] = set()

    def emit(kind, key, value):
        expected[kind].add(key)
        if audit_only:
            if store.read(kind, key) != value:
                raise IntegrityError(
                    "predicate record does not regenerate: " + kind + "/" + key
                )
        else:
            store.write(kind, key, value)

    print(
        json.dumps({"phase": "serial_source_effect_audits", "model_calls": 0}),
        flush=True,
    )
    training, diagnostic, audits = SOURCE["collect"](root)
    for name, audit in audits.items():
        emit("source_audits", name, audit)
    for role, rows in (("training", training), ("diagnostic", diagnostic)):
        for i, row in enumerate(rows):
            emit("examples", f"{role}-{i:02d}", row)
            emit("public_examples", row["public_digest"], row["public"])
    learned = LANG["learn"]([row["public"] for row in training])
    emit("construction", "two-pair", learned)
    for row in learned["enumeration"]:
        emit("clauses", digest(row["clause"]), row)
    vectors = []
    for row in diagnostic:
        try:
            vector = {
                "features": LANG["features"](row["public"]["program"]),
                "ast_digest": digest(LANG["ast_identity"](row["public"]["program"])),
                "error": None,
            }
        except (SyntaxError, ValueError, TypeError, RecursionError):
            vector = {
                "features": None,
                "ast_digest": None,
                "error": "unsupported_source",
            }
        vectors.append(vector)
        emit("feature_vectors", row["public_digest"], vector)
    train_keys = {overlap_key(row) for row in training}
    selected = [i for i, row in enumerate(diagnostic) if row["eligible"]]
    nonoverlap = [i for i in selected if overlap_key(diagnostic[i]) not in train_keys]
    exact_program_overlap = [
        i
        for i, row in enumerate(diagnostic)
        if digest(row["public"]["program"])
        in {digest(item["public"]["program"]) for item in training}
    ]
    clause_results, prediction_groups = [], defaultdict(list)
    for clause in learned["accepted_clauses"]:
        predictions = [
            LANG["classify"](clause, row["public"]["program"])["accepted"]
            for row in diagnostic
        ]
        if any(
            LANG["classify"](json.loads(json.dumps(clause)), row["public"]["program"])[
                "accepted"
            ]
            != p
            for row, p in zip(diagnostic, predictions, strict=True)
        ):
            raise IntegrityError("clause serialization changes predictions")

        def metrics(indices, predictions=predictions):
            return LANG["confusion"](
                [predictions[i] for i in indices],
                [diagnostic[i]["public"]["label"] for i in indices],
            )

        full, remainder = metrics(selected), metrics(nonoverlap)
        result = {
            "clause": clause,
            "predictions": predictions,
            "all_eligible": full,
            "without_exact_training_origin_program_overlap": remainder,
            "zero_diagnostic_errors": full["false_accept"]
            + full["false_reject"]
            + full["abstentions"]
            == 0,
        }
        emit("clause_diagnostics", digest(clause), result)
        clause_results.append(result)
        prediction_groups[digest(predictions)].append(digest(clause))
    leave_pair = []
    for pair in range(2):
        indices, other = [2 * pair, 2 * pair + 1], [2 * (1 - pair), 2 * (1 - pair) + 1]
        fitted = LANG["learn"]([training[i]["public"] for i in indices])
        comparisons = [
            {
                "clause": clause,
                "predictions": [
                    LANG["classify"](clause, training[i]["public"]["program"])[
                        "accepted"
                    ]
                    for i in other
                ],
            }
            for clause in fitted["accepted_clauses"]
        ]
        consistent = sum(
            row["predictions"] == [training[i]["public"]["label"] for i in other]
            for row in comparisons
        )
        item = {
            "training_pair": pair,
            "training_indices": indices,
            "diagnostic_indices": other,
            "construction": fitted,
            "comparisons": comparisons,
            "consistent_on_other_pair": consistent,
        }
        emit("leave_pair_out", str(pair), item)
        leave_pair.append(
            {
                "training_pair": pair,
                "accepted": len(comparisons),
                "consistent_on_other_pair": consistent,
            }
        )
    primary = sum(row["zero_diagnostic_errors"] for row in clause_results)
    report = {
        "protocol_digest": digest(protocol),
        "source_audit_digests": {name: digest(value) for name, value in audits.items()},
        "training_examples": len(training),
        "diagnostic_cells": len(diagnostic),
        "eligible_cells": len(selected),
        "ineligible_indices": [i for i in range(len(diagnostic)) if i not in selected],
        "parse_error_indices": [
            i for i, vector in enumerate(vectors) if vector["error"]
        ],
        "native_success_cells": sum(diagnostic[i]["public"]["label"] for i in selected),
        "exact_training_origin_program_overlap_indices": [
            i for i in selected if i not in nonoverlap
        ],
        "exact_training_program_overlap_indices": exact_program_overlap,
        "nonoverlap_cells": len(nonoverlap),
        "enumerated_clauses": len(learned["enumeration"]),
        "training_consistent_clauses": len(clause_results),
        "prediction_equivalence_groups": dict(sorted(prediction_groups.items())),
        "conflicting_feature_groups": conflicts(diagnostic, vectors, "features"),
        "conflicting_normalized_ast_groups": conflicts(
            diagnostic, vectors, "ast_digest"
        ),
        "leave_pair_out": leave_pair,
        "diagnostic_clauses": [
            {
                "clause_id": digest(row["clause"]),
                "all_eligible": row["all_eligible"],
                "nonoverlap": row["without_exact_training_origin_program_overlap"],
                "zero_diagnostic_errors": row["zero_diagnostic_errors"],
            }
            for row in clause_results
        ],
        "primary_metric": primary,
        "decision": "KEEP" if primary else "REVISE",
        "model_calls": 0,
        "native_executions": 0,
        "api_usd": 0,
        "admitted_contracts": 0,
        "limitation": "Post-outcome build diagnostic of syntactic classification against final-effect weak labels; not semantic boundary truth, learned scope or held-out efficacy.",
    }
    if (
        len(training) != protocol["training_examples"]
        or len(diagnostic) != protocol["diagnostic_cells"]
    ):
        raise IntegrityError("registered denominator changed")
    emit("reports", digest(report), report)
    for kind, keys in expected.items():
        if {p.stem for p in (store.root / kind).glob("*.json")} != keys:
            raise IntegrityError("missing or extra predicate records: " + kind)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store", type=Path, default=Path("artifacts/research/cycle19_code_predicates")
    )
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()
    report = run(RunStore(args.store), audit_only=args.audit_only)
    print(
        json.dumps(
            {
                "report_digest": digest(report),
                **{
                    key: report[key]
                    for key in (
                        "diagnostic_cells",
                        "eligible_cells",
                        "native_success_cells",
                        "nonoverlap_cells",
                        "enumerated_clauses",
                        "training_consistent_clauses",
                        "primary_metric",
                        "decision",
                        "model_calls",
                        "native_executions",
                        "api_usd",
                        "admitted_contracts",
                    )
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
