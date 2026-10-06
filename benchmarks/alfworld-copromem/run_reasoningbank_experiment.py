#!/usr/bin/env python3
"""Run ALFWorld through a thin adapter over upstream ReasoningBank."""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv

from reasoningbank_adapter import (
    DEFAULT_CHECKOUT,
    UPSTREAM_COMMIT,
    UPSTREAM_REPO,
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
    summarize,
    task_family,
    wsl_path,
    write_json,
    write_tracker,
)


DEFAULT_SOURCE_RUNS = (
    RESULTS_ROOT / "20261002T115943Z",
    RESULTS_ROOT / "20261003T015628Z-sorted-35-68",
)


def load_source_games(
    source_runs: Iterable[Path], limit: int | None
) -> tuple[list[Path], dict[str, Any]]:
    games: list[Path] = []
    manifests: list[dict[str, Any]] = []
    for run_dir in source_runs:
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        manifests.append(manifest)
        games.extend(Path(item) for item in manifest["games"])
    if not manifests:
        raise ValueError("at least one source run is required")
    if limit is not None:
        games = games[:limit]
    return games, manifests[0]


def restored_stats(summary_path: Path) -> ProviderStats:
    if not summary_path.exists():
        return ProviderStats()
    try:
        provider = json.loads(summary_path.read_text(encoding="utf-8")).get("provider") or {}
    except (OSError, json.JSONDecodeError):
        provider = {}
    return ProviderStats(
        calls=int(provider.get("calls", 0)),
        attempts=int(provider.get("attempts", 0)),
        retained_failed_reservations_usd=float(
            provider.get("retained_failed_reservations_usd", 0.0)
        ),
        charged_or_reserved_usd=float(provider.get("charged_or_reserved_usd", 0.0)),
    )


def upstream_usage(bank: Iterable[dict[str, Any]]) -> dict[str, Any]:
    records = list(bank)
    prompt_tokens = completion_tokens = total_tokens = 0
    reported_cost = 0.0
    calls_with_usage = 0
    for record in records:
        usage = (record.get("provider") or {}).get("usage") or {}
        if usage:
            calls_with_usage += 1
        prompt_tokens += int(usage.get("prompt_tokens") or 0)
        completion_tokens += int(usage.get("completion_tokens") or 0)
        total_tokens += int(usage.get("total_tokens") or 0)
        reported_cost += float(usage.get("cost") or 0.0)
    return {
        "induction_calls_with_usage": calls_with_usage,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "reported_cost_usd": reported_cost,
    }


def write_run_summary(
    path: Path,
    rows: list[dict[str, Any]],
    agent: OpenRouterAgent,
    bank: list[dict[str, Any]],
    adapter: ReasoningBankALFWorldAdapter,
) -> None:
    value = summarize(rows, agent.stats)
    value["reasoningbank"] = {
        "implementation": "upstream_adapter",
        "upstream_repo": UPSTREAM_REPO,
        "upstream_commit": adapter.commit,
        "memory_records": len(bank),
        "memory_items": sum(len(item.get("memory_items") or []) for item in bank),
        "embedding_model": adapter.embedding_model,
        "induction_provider": upstream_usage(bank),
        "budget_note": (
            "The provider block covers ALFWorld action calls. Upstream induction usage "
            "is reported separately; embedding usage is retained by OpenRouter."
        ),
    }
    write_json(path, value)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the official ReasoningBank memory loop through an ALFWorld adapter"
    )
    parser.add_argument("--source-runs", nargs="+", type=Path, default=list(DEFAULT_SOURCE_RUNS))
    parser.add_argument("--run-dir", type=Path, help="Resume an upstream-adapter run")
    parser.add_argument(
        "--rerun-failed",
        action="store_true",
        help="Rerun the latest failed tasks in an existing run after continuing it",
    )
    parser.add_argument(
        "--task-index",
        type=int,
        action="append",
        help="1-based task number to rerun in an existing run",
    )
    parser.add_argument("--tasks", type=int, default=None)
    parser.add_argument("--max-steps", type=int, default=60)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument(
        "--embedding-model", type=str, default="openai/text-embedding-3-small"
    )
    parser.add_argument("--induction-max-tokens", type=int, default=1024)
    parser.add_argument("--upstream-checkout", type=Path, default=DEFAULT_CHECKOUT)
    parser.add_argument(
        "--check", action="store_true", help="Validate ALFWorld and upstream imports without API calls"
    )
    args = parser.parse_args()

    if (args.rerun_failed or args.task_index) and not args.run_dir:
        raise SystemExit("--rerun-failed/--task-index require --run-dir")

    load_dotenv(ENV_FILE, override=False)
    source_runs = [Path(value) for value in args.source_runs]
    games, source_manifest = load_source_games(source_runs, args.tasks)
    seed = int(args.seed if args.seed is not None else source_manifest["seed"])
    model = args.model or str(source_manifest["model"])
    split = str(source_manifest["split"])
    data_dir = wsl_path(
        os.environ.get("ALFWORLD_DATA", str(DATA_ROOT))
    )
    os.environ["ALFWORLD_SPLIT"] = split
    os.environ["REASONING_BANK_EMBEDDING_MODEL"] = args.embedding_model
    config = load_config(data_dir, args.max_steps)

    if args.check:
        adapter = ReasoningBankALFWorldAdapter(
            model=model,
            bank_path=Path("/tmp/reasoningbank-check-bank.jsonl"),
            embeddings_path=Path("/tmp/reasoningbank-check-embeddings.jsonl"),
            checkout=args.upstream_checkout,
            max_tokens=args.induction_max_tokens,
        )
        from alfworld.agents.environment import get_environment

        manager = get_environment("AlfredTWEnv")(config, train_eval=split)
        manager.game_files = [str(games[0])]
        manager.num_games = 1
        env = manager.init_env(batch_size=1)
        try:
            observations, infos = env.reset()
            print(
                json.dumps(
                    {
                        "ok": True,
                        "implementation": "upstream_adapter",
                        "tasks": len(games),
                        "first_game": str(games[0]),
                        "first_task": extract_task(str(observations[0])),
                        "admissible_actions": len(infos["admissible_commands"][0]),
                        "max_steps": args.max_steps,
                        "upstream_checkout": str(adapter.checkout),
                        "upstream_commit": adapter.commit,
                    },
                    indent=2,
                )
            )
        finally:
            env.close()
        return 0

    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise SystemExit(f"OPENROUTER_API_KEY is blank. Add it to {ENV_FILE} and rerun.")

    if args.run_dir:
        run_dir = args.run_dir
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        implementation = (manifest.get("reasoningbank") or {}).get("implementation")
        if implementation != "upstream_adapter":
            raise SystemExit(
                "Refusing to mix the upstream adapter with a provisional ReasoningBank run. "
                "Start a new run directory."
            )
        games = [Path(value) for value in manifest["games"]]
        seed = int(manifest["seed"])
        model = str(manifest["model"])
        split = str(manifest["split"])
        max_steps = int(manifest["max_steps"])
        rb_config = manifest["reasoningbank"]
        embedding_model = str(rb_config["embedding_model"])
        induction_max_tokens = int(rb_config["induction_max_tokens"])
        upstream_checkout = Path(rb_config["upstream_checkout"])
        os.environ["REASONING_BANK_EMBEDDING_MODEL"] = embedding_model
        config = load_config(data_dir, max_steps)
    else:
        max_steps = int(args.max_steps)
        embedding_model = args.embedding_model
        induction_max_tokens = int(args.induction_max_tokens)
        upstream_checkout = args.upstream_checkout.resolve()
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_dir = RESULTS_ROOT / f"{run_id}-reasoningbank-upstream-alfworld"
        run_dir.mkdir(parents=True, exist_ok=False)
        manifest = {
            "run_id": run_id,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_runs": [str(value) for value in source_runs],
            "alfworld_commit": git_head(ALFWORLD_REPO),
            "copromem_commit": git_head(COPROMEM_REPO),
            "copromem_worktree_dirty": git_dirty(COPROMEM_REPO),
            "model": model,
            "split": split,
            "seed": seed,
            "task_count": len(games),
            "max_steps": max_steps,
            "difficulty_sort": True,
            "arms": ["reasoningbank"],
            "games": [str(game) for game in games],
            "reasoningbank": {
                "implementation": "upstream_adapter",
                "upstream_repo": UPSTREAM_REPO,
                "upstream_commit": UPSTREAM_COMMIT,
                "upstream_checkout": str(upstream_checkout),
                "upstream_functions": [
                    "WebArena.memory_management.select_memory",
                    "WebArena.induce_memory.format_trajectory",
                    "WebArena.induce_memory.CLIENT_DICT",
                    "WebArena.prompts.memory_instruction.SUCCESSFUL_SI",
                    "WebArena.prompts.memory_instruction.FAILED_SI",
                ],
                "retrieval_top_k": 1,
                "embedding_model": embedding_model,
                "induction_model": model,
                "induction_temperature": 1.0,
                "induction_max_items": 3,
                "induction_max_tokens": induction_max_tokens,
                "correctness_signal": "alfworld_environment_won",
                "trajectory_visibility": "observable_state_and_action_only",
            },
            "budget": {
                "max_calls": int(os.environ.get("ALFWORLD_MAX_CALLS", "12000")),
                "max_usd": float(os.environ.get("ALFWORLD_MAX_USD", "20.0")),
                "max_prompt_price_per_million": float(
                    os.environ.get("ALFWORLD_MAX_PROMPT_PRICE_PER_M", "1.0")
                ),
                "max_completion_price_per_million": float(
                    os.environ.get("ALFWORLD_MAX_COMPLETION_PRICE_PER_M", "3.0")
                ),
            },
        }
        write_json(run_dir / "manifest.json", manifest)

    budget = manifest.get("budget") or {}
    agent = OpenRouterAgent(
        api_key=api_key,
        model=model,
        max_calls=int(budget.get("max_calls", os.environ.get("ALFWORLD_MAX_CALLS", 12000))),
        max_usd=float(budget.get("max_usd", os.environ.get("ALFWORLD_MAX_USD", 20.0))),
        prompt_price_per_million=float(
            budget.get(
                "max_prompt_price_per_million",
                os.environ.get("ALFWORLD_MAX_PROMPT_PRICE_PER_M", 1.0),
            )
        ),
        completion_price_per_million=float(
            budget.get(
                "max_completion_price_per_million",
                os.environ.get("ALFWORLD_MAX_COMPLETION_PRICE_PER_M", 3.0),
            )
        ),
    )
    summary_path = run_dir / "summary.json"
    agent.stats = restored_stats(summary_path)
    rows_path = run_dir / "episodes.jsonl"
    bank_path = run_dir / "reasoning_bank.jsonl"
    adapter = ReasoningBankALFWorldAdapter(
        model=model,
        bank_path=bank_path,
        embeddings_path=run_dir / "query_embeddings.jsonl",
        checkout=upstream_checkout,
        max_tokens=induction_max_tokens,
    )
    rows = latest_episode_rows(read_jsonl(rows_path))
    bank = adapter.load_bank()
    bank_ids = {str(item.get("task_id")) for item in bank}
    failed_indices = {
        int(item["episode_index"])
        for item in rows
        if item.get("arm") == "reasoningbank" and not bool(item.get("success"))
    }
    if args.task_index:
        rerun_indices = {value - 1 for value in args.task_index}
        invalid = sorted(index for index in rerun_indices if index not in failed_indices)
        if invalid:
            raise SystemExit(
                "requested task(s) are not currently failed: "
                + ", ".join(str(index + 1) for index in invalid)
            )
    elif args.rerun_failed:
        rerun_indices = failed_indices
    else:
        rerun_indices = set()
    completed = {
        int(item["episode_index"])
        for item in rows
        if int(item["episode_index"]) not in rerun_indices
    }
    write_tracker(run_dir, manifest, rows, status="running")

    def track(current: dict[str, Any]) -> None:
        write_tracker(run_dir, manifest, rows, status="running", current=current)

    for row in sorted(rows, key=lambda item: int(item["episode_index"])):
        task_key = str(row["episode_index"])
        if task_key in bank_ids:
            continue
        track(
            {
                "arm": "reasoningbank",
                "episode_index": int(row["episode_index"]),
                "task_family": row["task_family"],
                "task": row["task"],
                "step": int(row["steps"]),
                "max_steps": max_steps,
                "phase": "upstream_memory_induction",
            }
        )
        record, provider = adapter.induce(row)
        record["provider"] = provider
        append_jsonl(bank_path, record)
        bank.append(record)
        bank_ids.add(task_key)

    from alfworld.agents.environment import get_environment

    manager = get_environment("AlfredTWEnv")(config, train_eval=split)
    try:
        random.seed(seed)
        np.random.seed(seed)
        for index, game in enumerate(games):
            if index in completed:
                print(f"[reasoningbank] skip {index + 1}/{len(games)} already recorded", flush=True)
                continue
            family = task_family(game)
            manager.game_files = [str(game)]
            manager.num_games = 1
            env = manager.init_env(batch_size=1)
            started = time.time()
            trajectory: list[dict[str, Any]] = []
            try:
                observations, infos = env.reset()
                observation = str(observations[0])
                task = extract_task(observation)
                track(
                    {
                        "arm": "reasoningbank",
                        "episode_index": index,
                        "task_family": family,
                        "task": task,
                        "step": 0,
                        "max_steps": max_steps,
                        "phase": "upstream_memory_retrieval",
                    }
                )
                retrieval_result = adapter.select(task_id=str(index), query=task)
                retrieval = retrieval_result.as_dict(adapter.embedding_model)
                won = False
                done = False
                for step in range(max_steps):
                    admissible = [str(value) for value in infos["admissible_commands"][0]]
                    track(
                        {
                            "arm": "reasoningbank",
                            "episode_index": index,
                            "task_family": family,
                            "task": task,
                            "step": step + 1,
                            "max_steps": max_steps,
                            "phase": "waiting_for_model",
                        }
                    )
                    before = observation
                    action, provider = agent.choose_action(
                        task,
                        observation,
                        admissible,
                        [
                            {"action": item["action"], "observation": item["observation"]}
                            for item in trajectory
                        ],
                        retrieval_result.guidance,
                        seed + index * 1000 + step,
                        guidance_label="REASONINGBANK MEMORY",
                    )
                    next_obs, _scores, dones, infos = env.step([action])
                    observation = str(next_obs[0])
                    done = bool(dones[0])
                    won = bool((infos.get("won") or [False])[0])
                    trajectory.append(
                        {
                            "step": step + 1,
                            "observation_before": before,
                            "action": action,
                            "observation": observation,
                            "done": done,
                            "won": won,
                            "provider": provider,
                        }
                    )
                    if done or won:
                        break

                row = {
                    "arm": "reasoningbank",
                    "episode_index": index,
                    "global_task_index": index + 1,
                    "task_id": str(game.relative_to(data_dir)),
                    "task_family": family,
                    "task": task,
                    "game_file": str(game),
                    "success": won,
                    "done": done,
                    "steps": len(trajectory),
                    "duration_seconds": round(time.time() - started, 3),
                    "retrieval": retrieval,
                    "trajectory": trajectory,
                }
                rows.append(row)
                completed.add(index)
                append_jsonl(rows_path, row)

                track(
                    {
                        "arm": "reasoningbank",
                        "episode_index": index,
                        "task_family": family,
                        "task": task,
                        "step": len(trajectory),
                        "max_steps": max_steps,
                        "phase": "upstream_memory_induction",
                    }
                )
                record, induction_provider = adapter.induce(row)
                record["provider"] = induction_provider
                append_jsonl(bank_path, record)
                bank.append(record)
                bank_ids.add(str(index))
                write_run_summary(summary_path, rows, agent, bank, adapter)
                write_tracker(run_dir, manifest, rows)
                print(
                    f"[reasoningbank] {index + 1}/{len(games)} success={won} "
                    f"steps={len(trajectory)} "
                    f"memories={sum(len(item.get('memory_items') or []) for item in bank)}",
                    flush=True,
                )
            finally:
                env.close()
    finally:
        try:
            manager.close()
        except Exception:
            pass

    write_run_summary(summary_path, rows, agent, bank, adapter)
    write_tracker(run_dir, manifest, rows, status="complete")
    print(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "implementation": "upstream_adapter",
                "completed": len(rows),
                "successes": sum(bool(item["success"]) for item in rows),
                "average_steps": (
                    sum(int(item["steps"]) for item in rows) / len(rows) if rows else 0.0
                ),
                "memory_records": len(bank),
                "upstream_commit": adapter.commit,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
