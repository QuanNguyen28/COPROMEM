"""Preregistered fixed planner/executor AppWorld source collection, train only."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import subprocess
from pathlib import Path

from .checkpoints import (
    GenerationService,
    IntegrityError,
    RecordedCallError,
    RunStore,
    canonical,
    digest,
    matched_seed,
)
from .providers import BudgetedOpenRouterClient, BudgetLedger, model_endpoints
from .real_gsm8k_experiment import load_env
from .stateful_adapter import (
    evaluate_worker_output,
    prepare_bundle,
    public_observation,
    run_worker,
    verify_prefix_pair,
)
from .stateful_stream import StreamWorker

PLANNER_SYSTEM = """You are the planner in a fixed planner/executor team solving a simulated AppWorld task. You see only the user's task and public code/tool history. Decide the next concrete information-gathering or state-changing step. Return ONLY JSON with keys intent (a short action plan), constraints (a list of task conditions that the next step must respect), and expected_effect (a short observable result). Do not output Python or hidden reasoning. Use observed API documentation; do not invent API signatures. An API error is observable feedback: the team may correct it on the next step. The task is solved by changing the simulated apps, not by describing what should happen. Do not request completion until the actual requested changes have been made. No access to evaluator tests, hidden databases, filesystem, internet or implementation internals is available."""

EXECUTOR_SYSTEM = """You are the executor in a fixed planner/executor AppWorld team. Implement the supplied short plan using the public task and observed API/code history. Return ONLY JSON {"code": "Python code"}. Code runs in a persistent Python interpreter with an apis object. Call APIs as apis.<app>.<api>(keyword_arguments). Discover tools with apis.api_docs.show_app_descriptions(), apis.api_docs.show_api_descriptions(app_name=...), apis.api_docs.show_api_doc(app_name=..., api_name=...), or apis.api_docs.search_api_docs(query=..., page_index=0, page_limit=5). Print focused relevant outputs, not whole large datasets. API responses are ordinary JSON-like dictionaries/lists. Variables persist across steps. Allowed imports: calendar, collections, copy, datetime, functools, itertools, json, math, pendulum, random, re. Do not import appworld, inspect internals, access files/network, use eval/exec/getattr/globals, mutate module/API attributes, or overwrite native bindings such as apis, print, json, datetime or random. Use error feedback and exact documented parameter names. Native datetime changes and implementation shortcuts are unavailable. When the user's requested app changes really are complete, call the documented supervisor completion API. Marking complete by itself does not accomplish the task. You have no evaluator or gold answer access."""

# Versioned shared onboarding. This is manually supplied interface knowledge, not
# learned memory. Preserve v1 strings above for auditing the frozen cycle-6 run.
PUBLIC_ONBOARDING_V2 = """AppWorld is a local simulation. The provided variable apis is already initialized: never import apis or install an app SDK. No real OAuth, internet or user interaction is needed. Every action is a small Python snippet in a persistent interpreter. Discover names and exact arguments instead of inventing methods. These helper calls are available:
print(apis.api_docs.show_app_descriptions())
print(apis.api_docs.show_api_descriptions(app_name='supervisor'))
print(apis.api_docs.show_api_doc(app_name='supervisor', api_name='show_account_passwords'))
print(apis.supervisor.show_profile())
The supervisor app provides the simulated user's identity, account passwords, addresses and payment cards. App login APIs return simulated tokens; obtain their exact signatures from documentation. Prior printed values and Python variables remain available. A rejected call is feedback that the next step may correct. Do not repeat an invalid API or import after it is rejected. Retrieve missing documentation before writing an app-specific operation. Print the information needed for the next decision. Paginated queries may require multiple pages. A file-system task refers to the file_system app APIs, never host files. Native time is available through datetime.datetime.now(); do not assume today's real date.
For modification tasks, carry out the requested app changes before completing. For information-only tasks, compute the requested answer and call apis.supervisor.complete_task(answer=answer); no unrelated app mutation is required. For a completed task needing no answer, use apis.supervisor.complete_task(). Completion alone is not evidence that the user's goal was met. Never complete after merely checking authentication or planning future work.
Only public APIs and permitted standard Python operations are available. Allowed imports: calendar, collections, copy, datetime, functools, itertools, json, math, pendulum, random, re. No filesystem/network, appworld imports, introspection, eval/exec/getattr/globals, or mutation of module/API attributes. Do not overwrite native bindings such as apis, print, json, datetime or random. There is no evaluator, hidden database access or gold solution. Keep each step small enough to inspect its result before proceeding."""


def role_prompts(settings: dict) -> tuple[str, str]:
    if settings.get("prompt_version", "v1") == "v1":
        return PLANNER_SYSTEM, EXECUTOR_SYSTEM
    if settings["prompt_version"] != "public-onboarding-v2":
        raise ValueError("unknown registered prompt version")
    return (
        "You are the planner in a fixed planner/executor team. Choose only the next small step, not an entire imagined solution. If an API signature or identity is unknown, plan a concrete public discovery call. Return ONLY JSON with intent (short string), constraints (list of short strings), and expected_effect (short string). No Python or hidden reasoning.\n"
        + PUBLIC_ONBOARDING_V2,
        "You are the executor in a fixed planner/executor team. Implement only the next small step in the supplied plan using documented APIs and observed values. Return ONLY raw executable Python: no JSON wrapper, Markdown fences or prose. Do not put a return statement at top level. Use concise code and print useful results. If the plan assumes an undocumented API, first inspect its public documentation.\n"
        + PUBLIC_ONBOARDING_V2,
    )


def parse_plan(text: str) -> tuple[dict, bool]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.splitlines()[1:-1])
    try:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise TypeError("plan is not an object")
        return value, False
    except (ValueError, TypeError):
        return {"intent": raw, "constraints": [], "expected_effect": ""}, True


def parse_code(text: str) -> tuple[str, bool]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.splitlines()[1:-1])
    try:
        value = json.loads(raw)
        if isinstance(value, dict) and isinstance(value.get("code"), str):
            return value["code"], False
    except ValueError:
        pass
    return raw, True


def parse_executor_response(text: str, settings: dict) -> tuple[str, bool]:
    if settings.get("executor_format", "json") == "json":
        return parse_code(text)
    raw = text.strip()
    formatted = raw.startswith("```")
    if formatted:
        lines = raw.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines)
    # Explicit compatibility parsing, never repair malformed Python or invent code.
    try:
        value = json.loads(raw)
        if isinstance(value, dict) and isinstance(value.get("code"), str):
            return value["code"], True
    except ValueError:
        pass
    return raw, formatted


def prompt_context(
    frame: dict,
    max_chars: int,
    *,
    output_chars: int = 4000,
    program_chars: int = 6000,
    step_budget: dict | None = None,
    source_retry_note: dict | None = None,
) -> dict:
    public = public_observation(frame)
    if step_budget is not None:
        public["step_budget"] = step_budget
    if source_retry_note is not None:
        public["source_retry_note"] = source_retry_note
    entries = []
    base = {**public, "history": [], "omitted_history_entries": len(public["history"])}
    if len(canonical(base)) > max_chars:
        raise ValueError("public task exceeds the declared context cap")
    for item in reversed(public["history"]):
        entry = {
            "program": item["program"][:program_chars],
            "output": item["output"][:output_chars],
            "truncated": len(item["output"]) > output_chars
            or len(item["program"]) > program_chars,
        }
        candidate = {
            **public,
            "history": list(reversed([*entries, entry])),
            "omitted_history_entries": len(public["history"]) - len(entries) - 1,
        }
        if len(canonical(candidate)) > max_chars:
            break
        entries.append(entry)
    return {
        **public,
        "history": list(reversed(entries)),
        "omitted_history_entries": len(public["history"]) - len(entries),
    }


def context_for_step(frame: dict, settings: dict, index: int) -> dict:
    """Versioned public presentation; old archives retain their exact contexts."""
    version = settings.get("context_version", "v1")
    if version == "v1":
        return prompt_context(frame, settings["context_chars"])
    if version not in {"public-history-budget-v2", "public-history-retry-v3"}:
        raise ValueError("unknown registered context version")
    if type(index) is not int or not 0 <= index < settings["max_steps"]:
        raise ValueError("step index outside the declared episode horizon")
    note = None
    if version == "public-history-retry-v3":
        note = settings["source_retry_note"]
        if note["task_id"] != frame["task_id"]:
            raise IntegrityError("source retry note belongs to another task")
    return prompt_context(
        frame,
        settings["context_chars"],
        output_chars=settings["history_output_chars"],
        program_chars=settings["history_program_chars"],
        step_budget={
            "total_action_steps": settings["max_steps"],
            "remaining_including_current": settings["max_steps"] - index,
        },
        source_retry_note=note,
    )


def transport_price_caps(settings: dict) -> dict[str, float]:
    """Declared route ceilings also bound every paid-attempt reservation."""
    caps = {
        "prompt_price_per_million": settings.get("prompt_price_per_million", 0.25),
        "completion_price_per_million": settings.get(
            "completion_price_per_million", 0.5
        ),
    }
    for name, value in caps.items():
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError("finite positive route price ceiling required: " + name)
    return caps


def validate_settings(settings: dict) -> None:
    transport_price_caps(settings)
    context_version = settings.get("context_version", "v1")
    if context_version not in {
        "v1",
        "public-history-budget-v2",
        "public-history-retry-v3",
    }:
        raise ValueError("unknown registered context version")
    for name in ("history_output_chars", "history_program_chars"):
        if context_version in {"public-history-budget-v2", "public-history-retry-v3"}:
            value = settings.get(name)
            if type(value) is not int or not 0 < value < settings["context_chars"]:
                raise ValueError(
                    "positive entry cap smaller than context required: " + name
                )
        elif name in settings:
            raise ValueError("entry-cap overrides require the new context version")
    version = settings.get("prompt_version", "v1")
    response_format = settings.get("executor_format", "json")
    if (version, response_format) not in {
        ("v1", "json"),
        ("public-onboarding-v2", "python"),
    }:
        raise ValueError("prompt and response-format versions must agree")
    if "07b42fd" not in settings["excluded_scenarios"]:
        raise ValueError("the oracle/diagnostic scenario must remain excluded")
    if type(settings["max_steps"]) is not int or not 1 <= settings["max_steps"] <= 50:
        raise ValueError("step cap must fit the shared worker limit")
    for name in (
        "build_groups",
        "replicates",
        "planner_tokens",
        "executor_tokens",
        "context_chars",
        "max_http_attempts",
    ):
        if type(settings[name]) is not int or settings[name] < 1:
            raise ValueError("positive integer required: " + name)
    for split in ("dev", "audit", "evaluation"):
        if (
            type(settings[split + "_groups"]) is not int
            or settings[split + "_groups"] < 0
        ):
            raise ValueError("nonnegative partition size required")
    if not 0 < settings["max_usd"] <= 5:
        raise ValueError("external pilot budget must be in (0, 5] USD")


def select_groups(native_data: Path, settings: dict) -> dict:
    task_ids = [
        line.strip().split(":")[0]
        for line in (native_data / "datasets/train.txt").read_text().splitlines()
        if line.strip()
    ]
    groups = sorted(
        {task_id.split("_")[0] for task_id in task_ids}
        - set(settings["excluded_scenarios"]),
        key=lambda group: digest([settings["selection_seed"], group]),
    )
    if "source_extension" in settings:
        extension = settings["source_extension"]
        if extension.get("version") != "unallocated-build-v1":
            raise ValueError("unknown source extension version")
        manifest_hash = hashlib.sha256(
            (native_data / "datasets/train.txt").read_bytes()
        ).hexdigest()
        if manifest_hash != extension["train_manifest_sha256"]:
            raise IntegrityError("train identifier manifest changed")
        prior_store = RunStore(Path(extension["registry_store"]))
        prior_protocol = prior_store.read("protocol", "preregistration")
        prior_selection = prior_store.read("dataset", "selection")
        if (
            prior_protocol is None
            or prior_selection is None
            or digest(prior_protocol) != extension["protocol_digest"]
            or digest(prior_selection) != extension["selection_digest"]
        ):
            raise IntegrityError("prior allocation registry digest mismatch")
        if "source_extension" in prior_protocol:
            raise ValueError("v1 extension requires an original allocation registry")
        for field in (
            "selection_seed",
            "excluded_scenarios",
            "dev_groups",
            "audit_groups",
            "evaluation_groups",
        ):
            if settings[field] != prior_protocol[field]:
                raise IntegrityError("source extension cannot change " + field)
        if select_groups(native_data, prior_protocol) != prior_selection:
            raise IntegrityError("prior allocation does not reproduce")
        allocated = {
            task_id.split("_")[0]
            for rows in prior_selection.values()
            for task_id in rows
        }
        chosen = [group for group in groups if group not in allocated][
            : settings["build_groups"]
        ]
        if len(chosen) != settings["build_groups"]:
            raise ValueError("insufficient unallocated train scenario groups")
        return {
            **{key: prior_selection[key] for key in ("dev", "audit", "evaluation")},
            "previous_build": prior_selection["build"],
            "build": [
                min(
                    (task_id for task_id in task_ids if task_id.split("_")[0] == group),
                    key=lambda task_id: int(task_id.split("_")[1]),
                )
                for group in chosen
            ],
        }
    selection, offset = {}, 0
    for split in ("build", "dev", "audit", "evaluation"):
        count = settings[split + "_groups"]
        chosen = groups[offset : offset + count]
        if len(chosen) != count:
            raise ValueError("insufficient disjoint train scenario groups")
        selection[split] = [
            min(
                (task_id for task_id in task_ids if task_id.split("_")[0] == group),
                key=lambda task_id: int(task_id.split("_")[1]),
            )
            for group in chosen
        ]
        offset += count
    return selection


def run_episode(
    worker,
    service: GenerationService,
    settings: dict,
    task_id: str,
    replicate: int,
    store: RunStore,
    episode_id: str,
) -> dict:
    if settings["max_steps"] > worker.last.get("action_limit", 20):
        raise ValueError(
            "registered horizon exceeds the running worker's action capacity"
        )
    steps = []
    failure = None
    planner_system, executor_system = role_prompts(settings)
    for index in range(settings["max_steps"]):
        if worker.last["completion_flag"]:
            break
        context = context_for_step(worker.last, settings, index)
        public_checkpoint = {"task_id": task_id, "public_context": context}
        checkpoint_id = digest(public_checkpoint)
        store.write("public_handoffs", checkpoint_id, public_checkpoint)
        try:
            planner = service.call(
                planner_system,
                canonical(context),
                settings["planner_tokens"],
                matched_seed(settings["seed"], task_id, f"planner-{index}", replicate),
            )
            plan, plan_fallback = parse_plan(planner.text)
            executor = service.call(
                executor_system,
                canonical({"public_context": context, "planner_handoff": plan}),
                settings["executor_tokens"],
                matched_seed(settings["seed"], task_id, f"executor-{index}", replicate),
            )
        except RecordedCallError as exc:
            failure = str(exc)
            break
        code, code_fallback = parse_executor_response(executor.text, settings)
        before_prefix = worker.last["request_id"]
        after = worker.act(code)
        step = {
            "episode_id": episode_id,
            "task_id": task_id,
            "scenario_id": task_id.split("_")[0],
            "replicate": replicate,
            "step": index,
            "public_checkpoint_id": checkpoint_id,
            "environment_prefix_id": before_prefix,
            "planner_generation_id": planner.request_id,
            "executor_generation_id": executor.request_id,
            "plan": plan,
            "code": code,
            "plan_parse_fallback": plan_fallback,
            "code_parse_fallback": code_fallback,
            "public_output": after["results"][-1]["output"],
            "local_action_error": after["results"][-1]["output"].startswith(
                "Execution failed."
            ),
            "completion_flag": after["completion_flag"],
        }
        store.write("source_steps", f"{episode_id}-{index:02d}", step)
        steps.append(step)
        print(
            json.dumps(
                {
                    "episode": episode_id,
                    "step": index + 1,
                    "action_error": step["local_action_error"],
                    "completion_flag": step["completion_flag"],
                }
            ),
            flush=True,
        )
    return {
        "episode_id": episode_id,
        "task_id": task_id,
        "scenario_id": task_id.split("_")[0],
        "replicate": replicate,
        "steps": len(steps),
        "local_action_errors": sum(step["local_action_error"] for step in steps),
        "provider_failure": failure,
        "completion_flag": worker.last["completion_flag"],
        "final_prefix_id": worker.last["request_id"],
        "partition": "build",
        "method": (
            "fixed_planner_executor_build_reflection_retry"
            if settings.get("context_version") == "public-history-retry-v3"
            else "fixed_planner_executor_no_memory"
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    settings = json.loads(args.config.read_text(encoding="utf-8"))
    validate_settings(settings)
    store = RunStore(Path(settings["output_directory"]))
    store.write("protocol", "preregistration", settings)
    sources = {
        str(path): path.read_text(encoding="utf-8")
        for path in sorted(
            [
                *Path("src/copromem").glob("*.py"),
                *Path("research/containers/appworld").glob("*.py"),
                Path("research/containers/appworld/Dockerfile"),
                Path("research/containers/appworld/requirements-linux-amd64.lock"),
            ]
        )
    }
    if "preregistration" in settings:
        path = Path(settings["preregistration"])
        sources[str(path)] = path.read_text(encoding="utf-8")
    provenance = {
        "commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "branch": subprocess.check_output(
            ["git", "branch", "--show-current"], text=True
        ).strip(),
        "python": platform.python_version(),
        "source_hashes": {key: digest(value) for key, value in sources.items()},
        "image_id": settings["image_id"],
    }
    store.bind_provenance(provenance)
    store.write("source_snapshots", digest(sources), sources)
    native_data = Path(settings["native_data"])
    selection = select_groups(native_data, settings)
    store.write("dataset", "selection", selection)
    if args.prepare_only:
        print(
            json.dumps(
                {
                    "protocol_digest": digest(settings),
                    "source_snapshot": digest(sources),
                    "selection": selection,
                    "paid_calls": 0,
                },
                indent=2,
            )
        )
        return
    bundle = store.root / "public_bundle"
    if not bundle.exists():
        prepare_bundle(native_data, bundle, selection["build"])
    if store.read("provider", "metadata") is None:
        store.write("provider", "metadata", model_endpoints(settings["model"]))
    key = load_env(args.env).get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not configured")
    ledger = BudgetLedger(store, settings["max_usd"], settings["max_http_attempts"])
    client = BudgetedOpenRouterClient(
        key,
        settings["model"],
        settings["provider"],
        ledger,
        **transport_price_caps(settings),
    )
    service = GenerationService(client, store, settings["cycle_id"])
    episodes = []
    stop = False
    for task_id in selection["build"]:
        for replicate in range(settings["replicates"]):
            episode_id = (
                f"{settings.get('episode_prefix', 'c06')}-{task_id}-r{replicate}"
            )
            existing = store.read("source_episodes", episode_id)
            if existing is not None:
                episodes.append(existing)
                continue
            if (store.root / "native" / episode_id).exists():
                raise RuntimeError(
                    "interrupted live episode requires audited recovery; no implicit overwrite/restart"
                )
            with StreamWorker(
                settings["image_id"],
                bundle,
                store,
                episode_id,
                task_id,
                settings["environment_seed"],
            ) as worker:
                episode = run_episode(
                    worker, service, settings, task_id, replicate, store, episode_id
                )
            result = store.read("worker_results", episode_id)
            if result is None:
                raise RuntimeError("worker ended without a valid recorded final state")
            evaluation = evaluate_worker_output(
                settings["image_id"], native_data, store, episode_id, task_id
            )
            episode["native_evaluation"] = evaluation
            # Reconstruct the recorded final prefix independently, with no LLM calls.
            replay_id = episode_id + "-replay"
            replay = run_worker(
                settings["image_id"],
                bundle,
                store,
                replay_id,
                store.read("worker_requests", episode_id),
            )
            replay_evaluation = None
            if replay.get("status") == "completed":
                replay_evaluation = evaluate_worker_output(
                    settings["image_id"], native_data, store, replay_id, task_id
                )
            error_indices = tuple(
                index
                for index, item in enumerate(result["results"])
                if item["output"].startswith("Execution failed.")
            )
            try:
                episode["replay_validation"] = verify_prefix_pair(
                    result, replay, expected_error_indices=error_indices
                )
                if evaluation != replay_evaluation:
                    raise ValueError("native evaluator differs between live and replay")
            except (ValueError, KeyError) as exc:
                episode["replay_validation"] = {
                    "verified": False,
                    "error_type": type(exc).__name__,
                    "reason": str(exc),
                }
            episode["eligible_for_induction"] = (
                episode["provider_failure"] is None
                and episode["replay_validation"]["verified"]
            )
            episode["replay_native_evaluation"] = replay_evaluation
            store.write("source_episodes", episode_id, episode)
            episodes.append(episode)
            print(
                json.dumps(
                    {
                        "episode": episode_id,
                        "native_success": evaluation["native_success"],
                        "replay_verified": episode["replay_validation"]["verified"],
                        "charged_or_reserved_usd": ledger.charged_or_reserved,
                    }
                ),
                flush=True,
            )
            if episode["provider_failure"]:
                stop = True
                break
        if stop:
            break
    report = {
        "cycle_id": settings["cycle_id"],
        "episodes": episodes,
        "native_successes": sum(
            item["native_evaluation"]["native_success"] for item in episodes
        ),
        "eligible_episodes": sum(item["eligible_for_induction"] for item in episodes),
        "physical_costs": service.costs(),
        "archived_completed_calls": len(list((store.root / "calls").glob("*.json"))),
        "settled_usd_all_invocations": sum(ledger.settlements.values()),
        "charged_or_reserved_usd": ledger.charged_or_reserved,
        "status": "source_collection_only_no_method_win",
        "decision": "REVISE",
        "limitations": [
            "Train/build only; no learned contract or held-out method comparison.",
            "Final failure is not a gold causal label of the planner handoff.",
            "Fixed shared action-language and context-window adaptation; not a published baseline reproduction.",
        ],
    }
    store.write("reports", digest(report), report)
    print(
        json.dumps(
            {
                "report_id": digest(report),
                "episodes": len(episodes),
                "native_successes": report["native_successes"],
                "eligible_episodes": report["eligible_episodes"],
                "charged_or_reserved_usd": ledger.charged_or_reserved,
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
