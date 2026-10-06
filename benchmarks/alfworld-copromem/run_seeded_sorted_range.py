#!/usr/bin/env python3
"""Run a sorted ALFWorld range with memory seeded from completed runs.

This runner is kept in the external benchmark harness.  It does not modify
ALFWorld, CoProMem, pinned ReMe, or upstream ReasoningBank.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import random
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from reasoningbank_adapter import (
    DEFAULT_CHECKOUT,
    ReasoningBankALFWorldAdapter,
    read_jsonl,
)
from run_experiment import (
    ALFWORLD_REPO,
    COPROMEM_REPO,
    DATA_ROOT,
    ENV_FILE,
    RESULTS_ROOT,
    OpenRouterAgent,
    ProviderStats,
    append_jsonl,
    extract_task,
    git_dirty,
    git_head,
    latest_episode_rows,
    load_config,
    np,
    run_episode,
    summarize,
    task_family,
    wsl_path,
    write_json,
)
from run_reme_experiment import LegacyRemeService, run_reme_episode, summarize_three_arms


EPISODE_KEY = re.compile(r"^alfworld:(\d+):(.*)$")


def _merge_unique(left: list[Any], right: list[Any]) -> list[Any]:
    result = copy.deepcopy(left)
    seen = {json.dumps(value, sort_keys=True, ensure_ascii=False) for value in result}
    for value in right:
        marker = json.dumps(value, sort_keys=True, ensure_ascii=False)
        if marker not in seen:
            result.append(copy.deepcopy(value))
            seen.add(marker)
    return result


def _rekey_episode(value: str, offset: int) -> str:
    match = EPISODE_KEY.match(value)
    if not match:
        return value
    return f"alfworld:{int(match.group(1)) + offset}:{match.group(2)}"


def _merge_episode_mapping(
    first: dict[str, Any], second: dict[str, Any], offset: int
) -> dict[str, Any]:
    result = copy.deepcopy(first)
    for key, value in second.items():
        result[_rekey_episode(str(key), offset)] = copy.deepcopy(value)
    return result


def merge_copromem_states(paths: list[Path]) -> dict[str, Any]:
    """Merge the two independent 34-task exports into one 1–68 state.

    The two historical runs used local episode numbers 0–33.  Episode-indexed
    maps from the second run are therefore re-keyed to 34–67.  Structural
    schemas and procedures are de-duplicated by their stable IDs.
    """
    states = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    merged = copy.deepcopy(states[0])
    learning = merged.setdefault("learning", {})
    for state_index, state in enumerate(states[1:], 1):
        source = state.get("learning") or {}
        offset = 34 if state_index == 1 else state_index * 34

        schema_by_id = {str(item.get("schema_id")): item for item in learning.get("schemas", [])}
        for item in source.get("schemas", []):
            schema_id = str(item.get("schema_id"))
            if schema_id not in schema_by_id:
                schema_by_id[schema_id] = copy.deepcopy(item)
                continue
            existing = schema_by_id[schema_id]
            old_stats = existing.get("structural_stats") or {}
            new_stats = item.get("structural_stats") or {}
            old_ids = list(old_stats.get("source_task_ids") or [])
            new_ids = list(new_stats.get("source_task_ids") or [])
            if old_ids or new_ids:
                old_stats["source_task_ids"] = _merge_unique(old_ids, new_ids)
                existing["structural_stats"] = old_stats
        learning["schemas"] = list(schema_by_id.values())

        procedure_by_id = {
            str(item.get("procedure_id")): item for item in learning.get("procedures", [])
        }
        for item in source.get("procedures", []):
            procedure_id = str(item.get("procedure_id"))
            procedure_by_id.setdefault(procedure_id, copy.deepcopy(item))
        learning["procedures"] = list(procedure_by_id.values())

        for name in (
            "episodes",
            "episode_schemas",
            "episode_procedures",
            "episode_success",
            "episode_step_evidence",
        ):
            learning[name] = _merge_episode_mapping(
                learning.get(name) or {}, source.get(name) or {}, offset
            )

        for name in ("feedback", "pending", "admission"):
            target = learning.setdefault(name, {})
            for key, value in (source.get(name) or {}).items():
                if isinstance(value, dict) and isinstance(target.get(key), dict):
                    target[key].update(copy.deepcopy(value))
                else:
                    target[key] = copy.deepcopy(value)

        for name in ("memories", "pending_memories", "schema_bank"):
            if isinstance(merged.get(name), list) and isinstance(state.get(name), list):
                merged[name] = _merge_unique(merged[name], state[name])
            elif isinstance(merged.get(name), dict) and isinstance(state.get(name), dict):
                merged[name].update(copy.deepcopy(state[name]))

    return merged


def merge_reme_snapshots(sources: list[Path], destination: Path) -> int:
    """Combine persisted ReMe records from both completed 34-task runs."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    records: dict[str, dict[str, Any]] = {}
    for source in sources:
        path = source / "alfworld-legacy-pilot.jsonl" if source.is_dir() else source
        if not path.exists():
            raise FileNotFoundError(f"ReMe seed snapshot not found: {path}")
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                continue
            key = str(value.get("memory_id") or json.dumps(value, sort_keys=True))
            records[key] = value
    with destination.open("w", encoding="utf-8") as handle:
        for value in records.values():
            handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
    return len(records)


def write_range_tracker(
    run_dir: Path,
    manifest: dict[str, Any],
    rows: list[dict[str, Any]],
    status: str,
    current: dict[str, Any] | None = None,
) -> None:
    rows = latest_episode_rows(rows)
    start = int(manifest["start_task"])
    end = int(manifest["end_task"])
    task_count = end - start + 1
    arms = list(manifest["arms"])
    expected = task_count * len(arms)

    def clean(value: Any) -> str:
        return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")

    lines = [
        "# ALFWorld seeded sorted-range tracker",
        "",
        f"- Status: **{status}**",
        f"- Updated (UTC): `{datetime.now(timezone.utc).isoformat(timespec='seconds')}`",
        f"- Run ID: `{clean(manifest['run_id'])}`",
        f"- Split: `{clean(manifest['split'])}`",
        f"- Model: `{clean(manifest['model'])}`",
        f"- Sorted task range: `{start}-{end}` of `{manifest.get('global_task_count', '?')}`",
        f"- Max steps per task: `{clean(manifest['max_steps'])}`",
        f"- Max tokens per model call: `{clean(manifest['max_tokens'])}`",
        "- Memory seeds: full completed tasks 1–68 for CoProMem, Legacy REmE, and ReasoningBank; none for no_memory",
        "",
        f"## Overall progress: {len(rows)}/{expected} episodes",
        "",
        "| Arm | Completed | Tasks | Successes | Success rate | Avg. steps |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for arm in arms:
        subset = [row for row in rows if row.get("arm") == arm]
        wins = sum(bool(row.get("success")) for row in subset)
        average = sum(int(row.get("steps", 0)) for row in subset) / len(subset) if subset else 0.0
        lines.append(
            f"| `{clean(arm)}` | {len(subset)} | {task_count} | {wins} | "
            f"{(wins / len(subset) if subset else 0.0):.1%} | {average:.2f} |"
        )
    if rows:
        last = rows[-1]
        lines.extend(
            [
                "",
                "## Last completed episode",
                "",
                f"- Arm: `{clean(last.get('arm'))}`",
                f"- Global task: `{clean(last.get('global_task_index', int(last.get('episode_index', 0)) + 1))}/{manifest.get('global_task_count', '?')}`",
                f"- Result: `{'success' if last.get('success') else 'failure'}`",
                f"- Steps: `{clean(last.get('steps'))}`",
            ]
        )
    failures = [row for row in rows if not row.get("success")]
    if failures:
        lines.extend(["", "## Failed episodes", "", "| Arm | Global task | Steps |", "|---|---:|---:|"])
        for row in failures:
            lines.append(
                f"| `{clean(row.get('arm'))}` | {clean(row.get('global_task_index', int(row.get('episode_index', 0)) + 1))} | {clean(row.get('steps'))} |"
            )
    if current:
        lines.extend(
            [
                "",
                "## Current episode",
                "",
                f"- Arm: `{clean(current.get('arm'))}`",
                f"- Global task: `{clean(current.get('global_task_index', int(current.get('episode_index', 0)) + 1))}/{manifest.get('global_task_count', '?')}`",
                f"- Step: `{clean(current.get('step'))}/{clean(current.get('max_steps'))}`",
                f"- Phase: `{clean(current.get('phase'))}`",
            ]
        )
        if current.get("action"):
            lines.append(f"- Last action: `{clean(current['action'])}`")
    (run_dir / "tracker.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def add_global(row: dict[str, Any], global_index: int) -> dict[str, Any]:
    row["global_task_index"] = global_index + 1
    return row


def read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def summary_with_reasoningbank(
    rows: list[dict[str, Any]],
    agent: OpenRouterAgent,
    reme: LegacyRemeService,
    bank: list[dict[str, Any]],
    adapter: ReasoningBankALFWorldAdapter,
) -> dict[str, Any]:
    value = summarize_three_arms(rows, agent.stats, reme)
    value["reasoningbank"] = {
        "implementation": "upstream_adapter",
        "upstream_commit": adapter.commit,
        "memory_records": len(bank),
        "memory_items": sum(len(item.get("memory_items") or []) for item in bank),
        "embedding_model": adapter.embedding_model,
        "seeded_from_completed_tasks": "1-68",
    }
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, default=None, help="Resume an existing seeded range run")
    parser.add_argument("--start-task", type=int, default=69)
    parser.add_argument("--end-task", type=int, default=100)
    parser.add_argument("--from-task", type=int, default=None, help="Resume only from this task within --run-dir")
    parser.add_argument("--to-task", type=int, default=None, help="Resume only through this task within --run-dir")
    parser.add_argument(
        "--arms",
        default="no_memory,copromem_v2,legacy_reme,reasoningbank",
        help="Comma-separated arms to run",
    )
    parser.add_argument("--max-steps", type=int, default=60)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--max-calls", type=int, default=12000)
    parser.add_argument("--max-usd", type=float, default=20.0)
    parser.add_argument("--port", type=int, default=8012)
    parser.add_argument("--seed-run", type=Path, default=RESULTS_ROOT / "20261002T115943Z")
    parser.add_argument(
        "--second-run",
        type=Path,
        default=RESULTS_ROOT / "20261003T015628Z-sorted-35-68",
    )
    parser.add_argument(
        "--reasoningbank-run",
        type=Path,
        default=RESULTS_ROOT / "20261003T143120Z-reasoningbank-upstream-alfworld",
    )
    parser.add_argument("--upstream-checkout", type=Path, default=DEFAULT_CHECKOUT)
    args = parser.parse_args()
    selected_arms = {item.strip() for item in args.arms.split(",") if item.strip()}
    valid_arms = {"no_memory", "copromem_v2", "legacy_reme", "reasoningbank"}
    unknown_arms = selected_arms - valid_arms
    if unknown_arms or not selected_arms:
        raise SystemExit(f"invalid --arms value: {sorted(unknown_arms) or 'empty'}")

    if args.start_task < 1 or args.end_task < args.start_task:
        raise SystemExit("invalid sorted task range")
    load_dotenv(ENV_FILE, override=False)
    os.environ["ALFWORLD_MAX_TOKENS"] = str(args.max_tokens)
    os.environ["ALFWORLD_REME_MAX_TOKENS"] = str(args.max_tokens)
    os.environ["ALFWORLD_MAX_CALLS"] = str(args.max_calls)
    os.environ["ALFWORLD_MAX_USD"] = str(args.max_usd)
    data_dir = wsl_path(os.environ.get("ALFWORLD_DATA", str(DATA_ROOT)))
    is_resume = args.run_dir is not None
    if is_resume:
        run_dir = args.run_dir
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        manifest_start_task = int(manifest["start_task"])
        manifest_end_task = int(manifest["end_task"])
        args.start_task = int(args.from_task or manifest_start_task)
        args.end_task = int(args.to_task or manifest_end_task)
        if not (manifest_start_task <= args.start_task <= args.end_task <= manifest_end_task):
            raise SystemExit(
                f"resume range {args.start_task}-{args.end_task} is outside "
                f"the run range {manifest_start_task}-{manifest_end_task}"
            )
        split = str(manifest["split"])
        seed = int(manifest["seed"])
        model = str(manifest["model"])
        args.max_steps = int(manifest["max_steps"])
        args.max_tokens = int(manifest["max_tokens"])
        all_games = [Path(value) for value in manifest["games"]]
        first_offset = args.start_task - manifest_start_task
        last_offset = args.end_task - manifest_start_task + 1
        games = all_games[first_offset:last_offset]
        source_manifest = manifest
        rows = read_rows(run_dir / "episodes.jsonl")
        order = [None] * int(manifest.get("global_task_count", args.end_task))
        reme_seed_path = None
    else:
        source_manifest = json.loads((args.seed_run / "manifest.json").read_text(encoding="utf-8"))
        split = str(source_manifest["split"])
        seed = int(source_manifest["seed"])
        model = str(source_manifest["model"])
        order_path = args.second_run / "difficulty_order.json"
        if order_path.exists():
            order = json.loads(order_path.read_text(encoding="utf-8"))
        else:
            from run_experiment import difficulty_order

            order = difficulty_order(data_dir, split)
        if len(order) < args.end_task:
            raise SystemExit(f"sorted list contains only {len(order)} tasks")
        games = [Path(item["game_file"]) for item in order[args.start_task - 1 : args.end_task]]
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_dir = RESULTS_ROOT / f"{run_id}-seeded-sorted-{args.start_task}-{args.end_task}"
        run_dir.mkdir(parents=True, exist_ok=False)

        copromem_state_paths = [args.seed_run / "copromem_state.json", args.second_run / "copromem_state.json"]
        merged_copromem = merge_copromem_states(copromem_state_paths)
        write_json(run_dir / "copromem_seed_1-68.json", merged_copromem)
        write_json(run_dir / "copromem_state.json", merged_copromem)

        reme_seed_dir = run_dir / "reme-seed-1-68"
        reme_seed_path = reme_seed_dir / "alfworld-legacy-pilot.jsonl"
        reme_memory_count = merge_reme_snapshots(
            [args.seed_run / "reme-task-memory", args.second_run / "reme-task-memory"],
            reme_seed_path,
        )
        rb_source_bank = args.reasoningbank_run / "reasoning_bank.jsonl"
        if not rb_source_bank.exists():
            raise SystemExit(f"ReasoningBank seed bank not found: {rb_source_bank}")
        shutil.copy2(rb_source_bank, run_dir / "reasoning_bank.jsonl")
        rb_embeddings = args.reasoningbank_run / "query_embeddings.jsonl"
        if rb_embeddings.exists():
            shutil.copy2(rb_embeddings, run_dir / "query_embeddings.jsonl")

        manifest = {
            "run_id": run_id,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "alfworld_commit": source_manifest["alfworld_commit"],
            "copromem_commit": source_manifest["copromem_commit"],
            "copromem_worktree_dirty": git_dirty(COPROMEM_REPO),
            "legacy_reme_source": source_manifest["legacy_reme_source"],
            "legacy_reme_commit": source_manifest["legacy_reme_commit"],
            "model": model,
            "split": split,
            "seed": seed,
            "task_count": len(games),
            "start_task": args.start_task,
            "end_task": args.end_task,
            "global_task_count": len(order),
            "max_steps": args.max_steps,
            "max_tokens": args.max_tokens,
            "difficulty_sort": True,
            "arms": ["no_memory", "copromem_v2", "legacy_reme", "reasoningbank"],
            "games": [str(game) for game in games],
            "memory_seeds": {
                "copromem": [str(path) for path in copromem_state_paths],
                "legacy_reme": [str(args.seed_run / "reme-task-memory"), str(args.second_run / "reme-task-memory")],
                "legacy_reme_records": reme_memory_count,
                "reasoningbank": str(rb_source_bank),
                "all_completed_tasks": "1-68",
            },
            "reasoningbank": {
                "implementation": "upstream_adapter",
                "upstream_checkout": str(args.upstream_checkout.resolve()),
                "embedding_model": os.environ.get("REASONING_BANK_EMBEDDING_MODEL", "openai/text-embedding-3-small"),
                "induction_max_tokens": args.max_tokens,
            },
            "budget": {
                "max_calls": args.max_calls,
                "max_usd": args.max_usd,
                "max_prompt_price_per_million": float(os.environ.get("ALFWORLD_MAX_PROMPT_PRICE_PER_M", "1.0")),
                "max_completion_price_per_million": float(os.environ.get("ALFWORLD_MAX_COMPLETION_PRICE_PER_M", "3.0")),
            },
        }
        write_json(run_dir / "manifest.json", manifest)
        rows = []

    os.environ["ALFWORLD_SPLIT"] = split
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise SystemExit(f"OPENROUTER_API_KEY is blank. Add it to {ENV_FILE} and rerun.")
    budget = manifest.get("budget") or {}
    agent = OpenRouterAgent(
        api_key=api_key,
        model=model,
        max_calls=int(budget.get("max_calls", args.max_calls)),
        max_usd=float(budget.get("max_usd", args.max_usd)),
        prompt_price_per_million=float(budget.get("max_prompt_price_per_million", os.environ.get("ALFWORLD_MAX_PROMPT_PRICE_PER_M", "1.0"))),
        completion_price_per_million=float(budget.get("max_completion_price_per_million", os.environ.get("ALFWORLD_MAX_COMPLETION_PRICE_PER_M", "3.0"))),
    )
    if is_resume and (run_dir / "summary.json").exists():
        prior = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        provider = prior.get("provider") or {}
        agent.stats = ProviderStats(
            calls=int(provider.get("calls", 0)),
            attempts=int(provider.get("attempts", 0)),
            retained_failed_reservations_usd=float(provider.get("retained_failed_reservations_usd", 0.0)),
            charged_or_reserved_usd=float(provider.get("charged_or_reserved_usd", 0.0)),
        )
    write_range_tracker(run_dir, manifest, rows, "running")
    config = load_config(data_dir, args.max_steps)
    events_path = run_dir / "episodes.jsonl"
    summary_path = run_dir / "summary.json"
    resume_reme_seed = run_dir / "reme-seed-1-68"
    reme = LegacyRemeService(
        run_dir / "resume-reme",
        model,
        args.port,
        state_dir=run_dir,
        seed_snapshot=reme_seed_path if not is_resume else (resume_reme_seed if resume_reme_seed.exists() else None),
    )
    adapter = ReasoningBankALFWorldAdapter(
        model=model,
        bank_path=run_dir / "reasoning_bank.jsonl",
        embeddings_path=run_dir / "query_embeddings.jsonl",
        checkout=args.upstream_checkout,
        max_tokens=args.max_tokens,
    )
    bank = adapter.load_bank()
    bank_ids = {str(item.get("task_id")) for item in bank}
    completed_keys = {
        (str(row.get("arm")), int(row.get("episode_index", -1)))
        for row in rows
        if row.get("arm") is not None and row.get("episode_index") is not None
    }

    def persist() -> None:
        write_json(summary_path, summary_with_reasoningbank(rows, agent, reme, bank, adapter))
        write_range_tracker(run_dir, manifest, rows, "running")

    def track(current: dict[str, Any]) -> None:
        write_range_tracker(run_dir, manifest, rows, "running", current)

    try:
        reme.run_dir.mkdir(parents=True, exist_ok=True)
        reme.start()
        from alfworld.agents.environment import get_environment

        for arm in ("no_memory", "copromem_v2"):
            if arm not in selected_arms:
                continue
            random.seed(seed)
            np.random.seed(seed)
            manager = get_environment("AlfredTWEnv")(config, train_eval=split)
            memory = None
            if arm == "copromem_v2":
                from copromem.copromem_memory_module import COPROMEMMemoryModule

                memory = COPROMEMMemoryModule(api_key="", seed_default_memories=False)
                memory.load_state(json.loads((run_dir / "copromem_state.json").read_text(encoding="utf-8")))
            try:
                for local_index, game in enumerate(games):
                    global_index = args.start_task - 1 + local_index
                    if (arm, global_index) in completed_keys:
                        print(f"[{arm}] skip task={global_index + 1} already recorded", flush=True)
                        continue
                    baseline = paired_baseline(rows, game, global_index) if arm == "copromem_v2" else None
                    row = add_global(
                        run_episode(
                            manager,
                            game,
                            arm,
                            global_index,
                            agent,
                            memory,
                            args.max_steps,
                            seed,
                            progress_callback=track,
                            baseline_score=baseline,
                        ),
                        global_index,
                    )
                    rows.append(row)
                    completed_keys.add((arm, global_index))
                    append_jsonl(events_path, row)
                    if memory is not None:
                        write_json(run_dir / "copromem_state.json", memory.export_state())
                    persist()
                    print(f"[{arm}] task={global_index + 1} success={row['success']} steps={row['steps']}", flush=True)
            finally:
                if hasattr(manager, "close"):
                    manager.close()

        if "legacy_reme" in selected_arms:
            random.seed(seed)
            np.random.seed(seed)
            manager = get_environment("AlfredTWEnv")(config, train_eval=split)
            try:
                for local_index, game in enumerate(games):
                    global_index = args.start_task - 1 + local_index
                    if ("legacy_reme", global_index) in completed_keys:
                        print(f"[legacy_reme] skip task={global_index + 1} already recorded", flush=True)
                        continue
                    row = add_global(
                        run_reme_episode(manager, game, global_index, agent, reme, args.max_steps, seed, progress_callback=track),
                        global_index,
                    )
                    rows.append(row)
                    completed_keys.add(("legacy_reme", global_index))
                    append_jsonl(events_path, row)
                    write_json(run_dir / "reme_service_events.json", reme.events)
                    persist()
                    print(f"[legacy_reme] task={global_index + 1} success={row['success']} steps={row['steps']}", flush=True)
            finally:
                if hasattr(manager, "close"):
                    manager.close()

        if "reasoningbank" in selected_arms:
            random.seed(seed)
            np.random.seed(seed)
            manager = get_environment("AlfredTWEnv")(config, train_eval=split)
            try:
                for local_index, game in enumerate(games):
                    global_index = args.start_task - 1 + local_index
                    if ("reasoningbank", global_index) in completed_keys:
                        print(f"[reasoningbank] skip task={global_index + 1} already recorded", flush=True)
                        continue
                    manager.game_files = [str(game)]
                    manager.num_games = 1
                    env = manager.init_env(batch_size=1)
                    started = time.time()
                    trajectory: list[dict[str, Any]] = []
                    try:
                        observations, infos = env.reset()
                        observation = str(observations[0])
                        task = extract_task(observation)
                        family = task_family(game)
                        retrieval_result = adapter.select(task_id=str(global_index), query=task)
                        won = False
                        done = False
                        for step in range(args.max_steps):
                            track({"arm": "reasoningbank", "global_task_index": global_index + 1, "step": step + 1, "max_steps": args.max_steps, "phase": "waiting_for_model"})
                            before = observation
                            action, provider = agent.choose_action(
                                task,
                                observation,
                                [str(value) for value in infos["admissible_commands"][0]],
                                [{"action": item["action"], "observation": item["observation"]} for item in trajectory],
                                retrieval_result.guidance,
                                seed + global_index * 1000 + step,
                                guidance_label="REASONINGBANK MEMORY",
                            )
                            next_obs, _scores, dones, infos = env.step([action])
                            observation = str(next_obs[0])
                            done = bool(dones[0])
                            won = bool((infos.get("won") or [False])[0])
                            trajectory.append({"step": step + 1, "observation_before": before, "action": action, "observation": observation, "done": done, "won": won, "provider": provider})
                            if done or won:
                                break
                        row = {
                            "arm": "reasoningbank",
                            "episode_index": global_index,
                            "global_task_index": global_index + 1,
                            "task_id": str(game.relative_to(data_dir)),
                            "task_family": family,
                            "task": task,
                            "game_file": str(game),
                            "success": won,
                            "done": done,
                            "steps": len(trajectory),
                            "duration_seconds": round(time.time() - started, 3),
                            "retrieval": retrieval_result.as_dict(adapter.embedding_model),
                            "trajectory": trajectory,
                        }
                        rows.append(row)
                        completed_keys.add(("reasoningbank", global_index))
                        append_jsonl(events_path, row)
                        record, provider = adapter.induce(row)
                        record["provider"] = provider
                        append_jsonl(run_dir / "reasoning_bank.jsonl", record)
                        bank = adapter.load_bank()
                        bank_ids.add(str(record.get("task_id")))
                        persist()
                        print(f"[reasoningbank] task={global_index + 1} success={row['success']} steps={row['steps']} memories={sum(len(item.get('memory_items') or []) for item in bank)}", flush=True)
                    finally:
                        env.close()
            finally:
                if hasattr(manager, "close"):
                    manager.close()
    finally:
        reme.close()

    write_json(summary_path, summary_with_reasoningbank(rows, agent, reme, bank, adapter))
    write_json(run_dir / "reme_service_events.json", reme.events)
    write_range_tracker(run_dir, manifest, rows, "complete")
    print(json.dumps({"run_dir": str(run_dir), "completed": len(rows), "expected": len(games) * 4}, indent=2), flush=True)
    return 0


def paired_baseline(rows: list[dict[str, Any]], game: Path, global_index: int) -> float | None:
    for row in reversed(rows):
        if row.get("arm") == "no_memory" and int(row.get("episode_index", -1)) == global_index and row.get("game_file") == str(game):
            return float(bool(row.get("success")))
    return None


if __name__ == "__main__":
    raise SystemExit(main())
