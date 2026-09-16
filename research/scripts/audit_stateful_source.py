"""Read-only source-corpus audit; optional append-only derived report, no model calls."""

from __future__ import annotations

import argparse
import ast
import json
from collections import Counter, defaultdict
from pathlib import Path

from copromem.checkpoints import IntegrityError, RunStore, canonical, digest
from copromem.reflection_source import retry_settings
from copromem.stateful_adapter import audit_prefix_runs
from copromem.stateful_source import (
    context_for_step,
    parse_executor_response,
    parse_plan,
)


def syntax_diagnostic(code: str) -> dict:
    """Syntax observations only; never treat no exception as successful work."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {"syntax_valid": False, "call_expressions": None, "api_paths": []}
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    paths = []
    for node in calls:
        parts, value = [], node.func
        while isinstance(value, ast.Attribute):
            parts.append(value.attr)
            value = value.value
        if isinstance(value, ast.Name) and value.id == "apis":
            paths.append(".".join(["apis", *reversed(parts)]))
    return {
        "syntax_valid": True,
        "call_expressions": len(calls),
        "api_paths": sorted(set(paths)),
    }


def objects(store: RunStore, kind: str) -> dict:
    return {
        path.stem: store.read(kind, path.stem)
        for path in sorted((store.root / kind).glob("*.json"))
    }


def audit(root: Path, *, native_pair_audit: bool = False) -> dict:
    store = RunStore(root)
    protocol = store.read("protocol", "preregistration")
    selection = store.read("dataset", "selection")
    if protocol is None or selection is None:
        raise IntegrityError("missing protocol or split selection")
    calls, steps, episodes = (
        objects(store, kind) for kind in ("calls", "source_steps", "source_episodes")
    )
    for key, value in calls.items():
        if (
            digest(value["request"]) != key
            or digest(value["response"]) != value["response_sha256"]
        ):
            raise IntegrityError("provider archive digest mismatch")
    totals = Counter()
    episode_steps = defaultdict(list)
    for key, step in steps.items():
        planner = calls[step["planner_generation_id"]]
        executor = calls[step["executor_generation_id"]]
        checkpoint = store.read("public_handoffs", step["public_checkpoint_id"])
        if checkpoint is None or digest(checkpoint) != step["public_checkpoint_id"]:
            raise IntegrityError("public handoff digest mismatch")
        plan, plan_fallback = parse_plan(planner["response"]["text"])
        code, code_fallback = parse_executor_response(
            executor["response"]["text"], protocol
        )
        if (plan, plan_fallback, code, code_fallback) != (
            step["plan"],
            step["plan_parse_fallback"],
            step["code"],
            step["code_parse_fallback"],
        ):
            raise IntegrityError("generation/parser evidence mismatch")
        context = checkpoint["public_context"]
        if planner["request"]["user"] != canonical(context) or executor["request"][
            "user"
        ] != canonical({"public_context": context, "planner_handoff": plan}):
            raise IntegrityError(
                "planner/executor did not use the recorded public boundary"
            )
        frame = store.read("stream_frames", f"{step['episode_id']}-{step['step']:03d}")
        after = store.read(
            "stream_frames", f"{step['episode_id']}-{step['step'] + 1:03d}"
        )
        if frame is None or after is None:
            raise IntegrityError("missing live boundary frame")
        runtime_settings = (
            retry_settings(protocol, store, step["task_id"])
            if protocol.get("context_version") == "public-history-retry-v3"
            else protocol
        )
        if (
            frame["request_id"] != step["environment_prefix_id"]
            or context_for_step(frame, runtime_settings, step["step"]) != context
        ):
            raise IntegrityError(
                "public checkpoint does not correspond to environment prefix"
            )
        if after["results"][-1] != {"program": code, "output": step["public_output"]}:
            raise IntegrityError(
                "recorded action/observation differs from native worker"
            )
        diagnostic = syntax_diagnostic(code)
        record = {"step_id": key, **diagnostic}
        episode_steps[step["episode_id"]].append(record)
        totals["steps"] += 1
        totals["plan_parse_fallbacks"] += plan_fallback
        totals["code_parse_fallbacks"] += code_fallback
        totals["local_action_errors"] += step["local_action_error"]
        totals["syntax_errors"] += not diagnostic["syntax_valid"]
        totals["syntax_valid_without_any_call"] += diagnostic["call_expressions"] == 0
        totals["steps_with_literal_api_call"] += bool(diagnostic["api_paths"])
    grouped = defaultdict(list)
    for episode_id, episode in episodes.items():
        if (
            episode["task_id"] not in selection["build"]
            or episode["scenario_id"] in protocol["excluded_scenarios"]
        ):
            raise IntegrityError("source task outside registered build split")
        if episode["steps"] != len(episode_steps[episode_id]):
            raise IntegrityError("episode step count mismatch")
        grouped[episode["scenario_id"]].append(episode)
        if native_pair_audit and episode["replay_validation"]["verified"]:
            errors = tuple(
                episode["replay_validation"]["expected_action_error_indices"]
            )
            audit_prefix_runs(
                store,
                [[episode_id, episode_id + "-replay"]],
                expected_error_indices=errors,
            )
    mixed = [
        group
        for group, rows in grouped.items()
        if {
            row["native_evaluation"]["native_success"]
            for row in rows
            if row["eligible_for_induction"]
        }
        == {True, False}
    ]
    finish = Counter(
        value["response"]["metadata"].get("finish_reason", "missing")
        for value in calls.values()
    )
    usage = {
        name: sum(value["response"]["usage"].get(name, 0) for value in calls.values())
        for name in (
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "usd",
            "latency_seconds",
        )
    }
    reservations, settlements = (
        objects(store, "reservations"),
        objects(store, "settlements"),
    )
    settled = sum(value["actual_usd"] for value in settlements.values())
    charged = sum(
        settlements.get(key, {}).get("actual_usd", value["reserved_usd"])
        for key, value in reservations.items()
    )
    if abs(usage["usd"] - settled) > 1e-9:
        raise IntegrityError("completed call usage and ledger settlements differ")
    expected = len(selection["build"]) * protocol["replicates"]
    return {
        "audit": "stateful-source-integrity-and-descriptive-errors-v1",
        "cycle_id": protocol["cycle_id"],
        "complete_registered_sample": len(episodes) == expected,
        "expected_episodes": expected,
        "episodes": list(episodes.values()),
        "recorded_episodes": len(episodes),
        "eligible_episodes": sum(
            row["eligible_for_induction"] for row in episodes.values()
        ),
        "native_successes": sum(
            row["native_evaluation"]["native_success"] for row in episodes.values()
        ),
        "mixed_outcome_scenarios": mixed,
        "primary_metric": len(mixed),
        "diagnostic_counts": dict(totals),
        "per_step_syntax_observations": dict(episode_steps),
        "completed_calls": len(calls),
        "finish_reasons": dict(finish),
        "usage": usage,
        "http_attempts": len(reservations),
        "unsettled_attempts": len(reservations.keys() - settlements.keys()),
        "charged_or_reserved_usd": charged,
        "native_pair_audit": native_pair_audit,
        "model_calls_for_audit": 0,
        "limitations": [
            "Syntax-derived counts are retrospective descriptive diagnostics, not the preregistered primary metric.",
            "A call expression may not execute; a caught API error may not have the worker failure prefix.",
            "No exception or completion flag alone establishes task success.",
            "No treatment comparison, learned contract, causal label or population superiority claim.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--native-pair-audit", action="store_true")
    args = parser.parse_args()
    report = audit(args.store, native_pair_audit=args.native_pair_audit)
    key = digest(report)
    RunStore(args.store).write("source_audits", key, report)
    summary = {
        k: v
        for k, v in report.items()
        if k not in {"episodes", "per_step_syntax_observations"}
    }
    print(json.dumps({"report_id": key, **summary}, indent=2))


if __name__ == "__main__":
    main()
