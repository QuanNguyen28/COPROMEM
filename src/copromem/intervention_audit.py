"""Offline observed repair-effect diagnostics; never train on final-test outcomes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .checkpoints import IntegrityError, RunStore, digest
from .paired_gsm8k import PairedConfig, paired_summary


def summarize_intervention(
    reference: list[dict[str, Any]],
    treatment: list[dict[str, Any]],
    config: PairedConfig,
) -> dict[str, Any]:
    """Keep task failure, schema violation, and response to repair distinct.

    Deltas are observed matched-draw effects, not an oracle of individual causal
    truth under stochastic inference. No model fitting or gate tuning occurs.
    """
    paired = paired_summary(reference, treatment, config)
    old = {(row["id"], row["replicate"]): row for row in reference}
    records = []
    for row in treatment:
        base = old[(row["id"], row["replicate"])]
        if base.get("failure") is not None or row.get("failure") is not None:
            raise ValueError(
                "provider failure must be resolved before repair-effect analysis"
            )
        if (
            base["solver_request_id"] == row["solver_request_id"]
            and base["correct"] != row["correct"]
        ):
            raise IntegrityError(
                "identical cached solver response cannot have different outcomes"
            )
        records.append(
            {
                "task_id": row["id"],
                "replicate": row["replicate"],
                "checkpoint_id": row["checkpoint_id"],
                "schema_violation": not row["initial_plan_valid"],
                "triggered": row["recovered"],
                "baseline_failure": not base["correct"],
                "observed_delta": int(row["correct"]) - int(base["correct"]),
                "same_solver_request": row["solver_request_id"]
                == base["solver_request_id"],
                "extra_logical_usd": sum(x["usd"] for x in row["logical_usage"])
                - sum(x["usd"] for x in base["logical_usage"]),
                "extra_logical_calls": row["calls"] - base["calls"],
            }
        )
    activated = [x for x in records if x["triggered"]]
    violations = [x for x in records if x["schema_violation"]]
    initial_successes = [x for x in records if not x["baseline_failure"]]
    return {
        "paired": paired,
        "activated_checkpoints": len(activated),
        "schema_violation_checkpoints": len(violations),
        "schema_failure_prediction_precision": sum(
            x["baseline_failure"] for x in violations
        )
        / len(violations)
        if violations
        else None,
        "schema_false_positive_rate_among_baseline_successes": sum(
            x["schema_violation"] for x in initial_successes
        )
        / len(initial_successes)
        if initial_successes
        else None,
        "observed_repair_benefit_rate_when_activated": sum(
            x["observed_delta"] > 0 for x in activated
        )
        / len(activated)
        if activated
        else None,
        "observed_repair_harm_rate_when_activated": sum(
            x["observed_delta"] < 0 for x in activated
        )
        / len(activated)
        if activated
        else None,
        "extra_logical_usd": sum(x["extra_logical_usd"] for x in records),
        "extra_logical_calls": sum(x["extra_logical_calls"] for x in records),
        "meets_minimal_descriptive_benefit_gate": paired["unique_tasks"] >= 4
        and paired["beneficial_flips"] >= 1
        and paired["harmful_flips"] == 0,
        "rows": records,
        "limitations": "Descriptive development diagnostic; repeated draws within a task are clustered. No learned policy, calibrated admission, generalization or exact causal truth is established.",
    }


def audit_report(report: dict[str, Any]) -> dict[str, Any]:
    protocol = report["protocol"]
    config = PairedConfig(**protocol["config"])
    if config.evaluation_role != "development":
        raise ValueError("this formulation diagnostic only accepts development data")
    if not protocol.get("shared_upstream_checkpoint"):
        raise ValueError(
            "unpaired historical reports are not valid repair-effect evidence"
        )
    reference = report["evaluation"]["no_memory"]["tasks"]
    summaries = {
        name: summarize_intervention(
            reference, report["evaluation"][name]["tasks"], config
        )
        for name in ("static_verifier", "sham_retry")
    }
    return {
        "audit": "observed-repair-effect-v1",
        "source_report_digest": digest(report),
        "partition": "development",
        "controls": summaries,
        "decision": "KEEP"
        if any(x["meets_minimal_descriptive_benefit_gate"] for x in summaries.values())
        else "REVISE",
        "new_api_calls": 0,
        "new_api_usd": 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output-store", type=Path, required=True)
    args = parser.parse_args()
    report = audit_report(json.loads(args.report.read_text(encoding="utf-8")))
    RunStore(args.output_store).write("intervention_audit", digest(report), report)
    display = dict(report)
    display["controls"] = {
        name: {
            key: value for key, value in item.items() if key not in {"rows", "paired"}
        }
        | {
            "paired": {
                key: value for key, value in item["paired"].items() if key != "details"
            }
        }
        for name, item in report["controls"].items()
    }
    print(json.dumps(display, indent=2))


if __name__ == "__main__":
    main()
