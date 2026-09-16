"""One frozen reflection-assisted build retry per previously allocated task."""

from __future__ import annotations

import argparse
import json
import platform
import runpy
import subprocess
from pathlib import Path

from copromem.checkpoints import (
    GenerationService,
    IntegrityError,
    RecordedCallError,
    RunStore,
    digest,
)
from copromem.providers import BudgetedOpenRouterClient, BudgetLedger, model_endpoints
from copromem.real_gsm8k_experiment import load_env
from copromem.reflection_source import create_note, reflection_input, retry_settings
from copromem.stateful_adapter import (
    evaluate_worker_output,
    prepare_bundle,
    run_worker,
    verify_prefix_pair,
)
from copromem.stateful_source import (
    run_episode,
    transport_price_caps,
    validate_settings,
)
from copromem.stateful_stream import StreamWorker


def gather_sources(settings: dict) -> tuple[dict, dict]:
    audit_fn = runpy.run_path(
        str(Path(__file__).with_name("audit_stateful_source.py"))
    )["audit"]
    sources, reserved, seen_scenarios = {}, None, set()
    for entry in settings["prior_sources"]:
        prior = RunStore(Path(entry["store"]))
        protocol = prior.read("protocol", "preregistration")
        selection = prior.read("dataset", "selection")
        audit = prior.read("source_audits", entry["audit_id"])
        if (
            digest(protocol) != entry["protocol_digest"]
            or digest(selection) != entry["selection_digest"]
            or audit is None
            or digest(audit) != entry["audit_id"]
            or not audit["complete_registered_sample"]
            or audit_fn(prior.root, native_pair_audit=True) != audit
        ):
            raise IntegrityError("prior complete corpus or native audit changed")
        current_reserved = {
            key: selection[key] for key in ("dev", "audit", "evaluation")
        }
        if reserved is None:
            reserved = current_reserved
        if reserved != current_reserved:
            raise IntegrityError("prior reserved allocations disagree")
        for field in (
            "image_id",
            "model",
            "provider",
            "prompt_version",
            "executor_format",
            "history_output_chars",
            "history_program_chars",
            "seed",
            "environment_seed",
            "max_steps",
            "planner_tokens",
            "executor_tokens",
            "context_chars",
            "excluded_scenarios",
        ):
            if protocol[field] != settings[field]:
                raise IntegrityError("unregistered source workflow change: " + field)
        for task_id in selection["build"]:
            scenario = task_id.split("_")[0]
            if scenario in seen_scenarios or scenario in settings["excluded_scenarios"]:
                raise IntegrityError("duplicate or excluded build scenario")
            seen_scenarios.add(scenario)
            rows = [row for row in audit["episodes"] if row["task_id"] == task_id]
            chosen = [
                row
                for row in rows
                if row["replicate"] == settings["reflection_source_replicate"]
            ]
            if (
                len(chosen) != 1
                or not chosen[0]["eligible_for_induction"]
                or chosen[0]["partition"] != "build"
            ):
                raise IntegrityError(
                    "fixed source replicate is missing or ineligible; no substitution"
                )
            episode = chosen[0]
            frame = prior.read("worker_results", episode["episode_id"])
            payload = reflection_input(
                frame, episode["native_evaluation"]["native_success"], settings
            )
            sources[task_id] = {
                "task_id": task_id,
                "episode_id": episode["episode_id"],
                "prior_store": entry["store"],
                "prior_audit_id": entry["audit_id"],
                "source_episode_digest": digest(episode),
                "source_frame_digest": digest(frame),
                "reflection_input": payload,
                "prior_eligible_outcomes": [
                    row["native_evaluation"]["native_success"]
                    for row in rows
                    if row["eligible_for_induction"]
                ],
            }
    if len(sources) != settings["build_groups"]:
        raise IntegrityError("registered retry task count mismatch")
    if seen_scenarios & {
        task.split("_")[0] for values in reserved.values() for task in values
    }:
        raise IntegrityError("reserved scenario selected for retry")
    return sources, {"build": list(sources), **reserved}


def collect_retry(
    settings: dict,
    store: RunStore,
    service: GenerationService,
    bundle: Path,
    task_id: str,
) -> dict:
    episode_id = f"c15-{task_id}-r{settings['retry_replicate']}"
    existing = store.read("source_episodes", episode_id)
    if existing is not None:
        return existing
    if (store.root / "native" / episode_id).exists():
        raise IntegrityError(
            "partial live retry needs audited recovery; no automatic restart"
        )
    runtime = retry_settings(settings, store, task_id)
    with StreamWorker(
        settings["image_id"],
        bundle,
        store,
        episode_id,
        task_id,
        settings["environment_seed"],
    ) as worker:
        episode = run_episode(
            worker,
            service,
            runtime,
            task_id,
            settings["retry_replicate"],
            store,
            episode_id,
        )
    first = store.read("worker_results", episode_id)
    if first is None:
        raise IntegrityError("live retry ended without a complete worker record")
    native_data = Path(settings["native_data"])
    evaluation = evaluate_worker_output(
        settings["image_id"], native_data, store, episode_id, task_id
    )
    replay_id = episode_id + "-replay"
    second = run_worker(
        settings["image_id"],
        bundle,
        store,
        replay_id,
        store.read("worker_requests", episode_id),
    )
    replay_evaluation = (
        evaluate_worker_output(
            settings["image_id"], native_data, store, replay_id, task_id
        )
        if second.get("status") == "completed"
        else None
    )
    errors = tuple(
        index
        for index, item in enumerate(first["results"])
        if item["output"].startswith("Execution failed.")
    )
    try:
        validation = verify_prefix_pair(first, second, expected_error_indices=errors)
        if evaluation != replay_evaluation:
            raise IntegrityError(
                "native evaluator differs between live and retry replay"
            )
    except (ValueError, KeyError) as exc:
        validation = {
            "verified": False,
            "error_type": type(exc).__name__,
            "reason": str(exc),
        }
    episode.update(
        native_evaluation=evaluation,
        replay_native_evaluation=replay_evaluation,
        replay_validation=validation,
        eligible_for_induction=episode["provider_failure"] is None
        and validation["verified"],
    )
    store.write("source_episodes", episode_id, episode)
    return episode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("research/configs/cycle15_reflection_source.json"),
    )
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    settings = json.loads(args.config.read_text(encoding="utf-8"))
    validate_settings(settings)
    if (
        settings["context_version"] != "public-history-retry-v3"
        or settings["replicates"] != 1
        or settings["reflection_source_replicate"] != 0
        or settings["retry_replicate"] != 2
    ):
        raise ValueError("only the preregistered one-retry source design is supported")
    for key, ceiling in (
        ("reflection_tokens", 512),
        ("reflection_note_chars", 4000),
        ("reflection_context_chars", 64000),
    ):
        if type(settings[key]) is not int or not 0 < settings[key] <= ceiling:
            raise ValueError("invalid reflection budget: " + key)
    store = RunStore(Path(settings["output_directory"]))
    sources, selection = gather_sources(settings)
    texts = {
        str(path): path.read_text(encoding="utf-8")
        for path in [
            *sorted(Path("src/copromem").glob("*.py")),
            Path(__file__),
            Path(settings["preregistration"]),
            Path(__file__).with_name("audit_stateful_source.py"),
            *sorted(Path("research/containers/appworld").glob("*.py")),
            Path("research/containers/appworld/Dockerfile"),
            Path("research/containers/appworld/requirements-linux-amd64.lock"),
        ]
    }
    provenance = {
        "branch": subprocess.check_output(
            ["git", "branch", "--show-current"], text=True
        ).strip(),
        "commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "python": platform.python_version(),
        "protocol_digest": digest(settings),
        "source_hashes": {key: digest(value) for key, value in texts.items()},
    }
    if provenance["branch"] != "codex/copromem-research-loop":
        raise IntegrityError("wrong research branch")
    store.bind_provenance(provenance)
    store.write("protocol", "preregistration", settings)
    store.write("source_snapshots", digest(texts), texts)
    store.write("dataset", "selection", selection)
    store.write(
        "reflection_allocation",
        "sources",
        {
            "sources": {key: digest(value) for key, value in sources.items()},
            "source_replicate": 0,
            "selection_digest": digest(selection),
        },
    )
    for task_id, source in sources.items():
        store.write("reflection_sources", task_id, source)
    if args.prepare_only:
        print(
            json.dumps(
                {
                    "protocol_digest": digest(settings),
                    "source_snapshot": digest(texts),
                    "selection": selection,
                    "prior_mixed_tasks": [
                        task
                        for task, source in sources.items()
                        if set(source["prior_eligible_outcomes"]) == {False, True}
                    ],
                    "paid_calls": 0,
                },
                indent=2,
            )
        )
        return
    bundle = store.root / "public_bundle"
    if not bundle.exists():
        prepare_bundle(Path(settings["native_data"]), bundle, selection["build"])
    if store.read("provider", "metadata") is None:
        store.write("provider", "metadata", model_endpoints(settings["model"]))
    key = load_env(args.env).get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")
    ledger = BudgetLedger(store, settings["max_usd"], settings["max_http_attempts"])
    client = BudgetedOpenRouterClient(
        key,
        settings["model"],
        settings["provider"],
        ledger,
        **transport_price_caps(settings),
    )
    service = GenerationService(client, store, settings["cycle_id"])
    episodes, failure = [], None
    for task_id, source in sources.items():
        try:
            if store.read("source_retry_notes", task_id) is None:
                create_note(service, store, settings, source)
            episode = collect_retry(settings, store, service, bundle, task_id)
        except RecordedCallError as exc:
            failure = str(exc)
            break
        episodes.append(episode)
        print(
            json.dumps(
                {
                    "episode": episode["episode_id"],
                    "native_success": episode["native_evaluation"]["native_success"],
                    "eligible": episode["eligible_for_induction"],
                    "charged_or_reserved_usd": ledger.charged_or_reserved,
                }
            ),
            flush=True,
        )
        if episode["provider_failure"]:
            failure = episode["provider_failure"]
            break
    new_mixed = [
        row["task_id"]
        for row in episodes
        if row["eligible_for_induction"]
        and set(sources[row["task_id"]]["prior_eligible_outcomes"]) != {False, True}
        and {
            *sources[row["task_id"]]["prior_eligible_outcomes"],
            row["native_evaluation"]["native_success"],
        }
        == {False, True}
    ]
    report = {
        "protocol_digest": digest(settings),
        "episodes": episodes,
        "complete_registered_sample": len(episodes) == len(sources),
        "new_mixed_tasks": new_mixed,
        "primary_metric": len(new_mixed),
        "native_successes": sum(
            row["native_evaluation"]["native_success"] for row in episodes
        ),
        "eligible_episodes": sum(row["eligible_for_induction"] for row in episodes),
        "provider_failure": failure,
        "completed_calls": len(list((store.root / "calls").glob("*.json"))),
        "settled_usd": sum(ledger.settlements.values()),
        "charged_or_reserved_usd": ledger.charged_or_reserved,
        "decision": "KEEP"
        if new_mixed and failure is None and len(episodes) == len(sources)
        else "REVISE",
        "status": "build_source_acquisition_only_no_learned_contract_or_reflection_efficacy_claim",
    }
    store.write("reports", digest(report), report)
    print(
        json.dumps(
            {
                "report_id": digest(report),
                **{key: value for key, value in report.items() if key != "episodes"},
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
