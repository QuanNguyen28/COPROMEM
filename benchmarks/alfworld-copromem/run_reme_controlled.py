#!/usr/bin/env python3
"""Run a ReMe-only ALFWorld experiment with memory hygiene and fallback recovery."""

from __future__ import annotations

import argparse
import json
import os
import random
import traceback
import time
from pathlib import Path

from dotenv import load_dotenv

from run_experiment import (
    ALFWORLD_REPO,
    COPROMEM_REPO,
    DATA_ROOT,
    ENV_FILE,
    RESULTS_ROOT,
    OpenRouterAgent,
    ProviderStats,
    append_jsonl,
    git_dirty,
    git_head,
    latest_episode_rows,
    load_config,
    np,
    select_games_by_difficulty,
    summarize,
    wsl_path,
    write_json,
    write_tracker,
)
from run_reme_experiment import (
    DEFAULT_REME_SOURCE,
    LegacyRemeService,
    run_reme_episode,
    summarize_three_arms,
)


def record_runner_error(run_dir: Path, phase: str, exc: BaseException) -> None:
    """Persist exceptions because hidden WSL launches do not retain stderr."""
    path = run_dir / "runner-errors.log"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            f"\n[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] {phase}: "
            f"{type(exc).__name__}: {exc}\n"
        )
        traceback.print_exception(type(exc), exc, exc.__traceback__, file=handle)
        handle.flush()


def write_progress_artifacts(
    run_dir: Path,
    manifest: dict,
    rows: list[dict],
    agent: OpenRouterAgent,
    reme: LegacyRemeService,
) -> None:
    """Keep one bookkeeping failure from terminating the benchmark."""
    try:
        write_json(run_dir / "summary.json", summarize_three_arms(rows, agent.stats, reme))
    except Exception as exc:
        record_runner_error(run_dir, "summary_write", exc)
    try:
        write_json(run_dir / "reme_service_events.json", reme.events)
    except Exception as exc:
        record_runner_error(run_dir, "service_events_write", exc)
    try:
        write_tracker(run_dir, manifest, rows, status="running")
    except Exception as exc:
        record_runner_error(run_dir, "tracker_write", exc)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=int, default=100)
    parser.add_argument("--run-dir", type=Path, default=None,
                        help="Resume an existing controlled run in place.")
    parser.add_argument("--max-steps", type=int, default=60)
    parser.add_argument("--seed", type=int, default=1108)
    parser.add_argument("--port", type=int, default=8014)
    parser.add_argument("--cleanup-every", type=int, default=5)
    parser.add_argument("--freq-threshold", type=int, default=5)
    parser.add_argument("--utility-threshold", type=float, default=0.5)
    parser.add_argument("--fallback-retry-after", type=int, default=2)
    parser.add_argument("--fallback-disable-guidance-after", type=int, default=3)
    parser.add_argument("--fallback-retry-tokens", type=int, default=256)
    args = parser.parse_args()

    if args.tasks < 1 or args.max_steps < 1:
        raise ValueError("tasks and max steps must be positive")
    if args.cleanup_every < 1:
        raise ValueError("cleanup interval must be positive")

    load_dotenv(ENV_FILE, override=False)
    os.environ.setdefault("ALFWORLD_MAX_TOKENS", "1024")
    data_dir = wsl_path(
        os.environ.get("ALFWORLD_DATA", str(DATA_ROOT))
    )
    split = os.environ.get("ALFWORLD_SPLIT", "eval_out_of_distribution")
    os.environ["ALFWORLD_SPLIT"] = split
    random.seed(args.seed)
    np.random.seed(args.seed)

    resume_dir = args.run_dir.resolve() if args.run_dir else None
    if resume_dir is not None:
        manifest_path = resume_dir / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Cannot resume without {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        split = str(manifest.get("split", split))
        os.environ["ALFWORLD_SPLIT"] = split
        args.seed = int(manifest.get("seed", args.seed))
        args.max_steps = int(manifest.get("max_steps", args.max_steps))
        games = [Path(game) for game in manifest.get("games", [])]
        difficulty_path = resume_dir / "difficulty_order.json"
        difficulty_rows = json.loads(difficulty_path.read_text(encoding="utf-8")) if difficulty_path.exists() else []
        if not games:
            raise ValueError(f"No games listed in {manifest_path}")
    else:
        config = load_config(data_dir, args.max_steps)
        games, difficulty_rows = select_games_by_difficulty(data_dir, split, args.tasks)

    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise SystemExit(f"OPENROUTER_API_KEY is blank. Add it to {ENV_FILE} and rerun.")
    if resume_dir is not None:
        max_tokens = int(manifest.get("max_tokens", os.environ.get("ALFWORLD_MAX_TOKENS", "1024")))
        os.environ["ALFWORLD_MAX_TOKENS"] = str(max_tokens)
    agent = OpenRouterAgent(
        api_key=api_key,
        model=os.environ.get("ALFWORLD_MODEL", "deepseek/deepseek-v4-flash-0731"),
        max_calls=int(os.environ.get("ALFWORLD_MAX_CALLS", "12000")),
        max_usd=float(os.environ.get("ALFWORLD_MAX_USD", "20.0")),
        prompt_price_per_million=float(os.environ.get("ALFWORLD_MAX_PROMPT_PRICE_PER_M", "1.0")),
        completion_price_per_million=float(os.environ.get("ALFWORLD_MAX_COMPLETION_PRICE_PER_M", "3.0")),
    )

    if resume_dir is not None:
        run_dir = resume_dir
        run_dir.mkdir(parents=True, exist_ok=True)
        args.cleanup_every = int(manifest.get("controls", {}).get("memory_cleanup", {}).get(
            "every_completed_episodes", args.cleanup_every
        ))
        args.freq_threshold = int(manifest.get("controls", {}).get("memory_cleanup", {}).get(
            "freq_threshold", args.freq_threshold
        ))
        args.utility_threshold = float(manifest.get("controls", {}).get("memory_cleanup", {}).get(
            "utility_threshold", args.utility_threshold
        ))
        fallback = manifest.get("controls", {}).get("fallback_recovery", {})
        args.fallback_retry_after = int(fallback.get("retry_after_consecutive_fallbacks", args.fallback_retry_after))
        args.fallback_disable_guidance_after = int(fallback.get("disable_memory_guidance_after", args.fallback_disable_guidance_after))
        args.fallback_retry_tokens = int(fallback.get("retry_max_tokens", args.fallback_retry_tokens))
    else:
        run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        run_dir = RESULTS_ROOT / f"{run_id}-reme-controlled-1-{len(games)}"
        run_dir.mkdir(parents=True, exist_ok=False)
        manifest = {
            "run_id": run_id,
            "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "alfworld_commit": git_head(ALFWORLD_REPO),
            "copromem_commit": git_head(COPROMEM_REPO),
            "copromem_worktree_dirty": git_dirty(COPROMEM_REPO),
            "legacy_reme_source": str(DEFAULT_REME_SOURCE),
            "legacy_reme_commit": git_head(DEFAULT_REME_SOURCE),
            "model": agent.model,
            "split": split,
            "seed": args.seed,
            "task_count": len(games),
            "max_steps": args.max_steps,
            "max_tokens": int(os.environ.get("ALFWORLD_MAX_TOKENS", "1024")),
            "arms": ["legacy_reme"],
            "memory_seed": "fresh_empty_bank",
            "difficulty_sort": True,
            "games": [str(game) for game in games],
            "controls": {
                "memory_cleanup": {
                    "enabled": True,
                    "every_completed_episodes": args.cleanup_every,
                    "freq_threshold": args.freq_threshold,
                    "utility_threshold": args.utility_threshold,
                },
                "fallback_recovery": {
                    "enabled": True,
                    "retry_after_consecutive_fallbacks": args.fallback_retry_after,
                    "disable_memory_guidance_after": args.fallback_disable_guidance_after,
                    "retry_max_tokens": args.fallback_retry_tokens,
                },
            },
            "budget": {
                "max_calls": agent.max_calls,
                "max_usd": agent.max_usd,
                "max_prompt_price_per_million": agent.prompt_price,
                "max_completion_price_per_million": agent.completion_price,
            },
        }
        write_json(run_dir / "manifest.json", manifest)
        write_json(run_dir / "difficulty_order.json", difficulty_rows)
    events_path = run_dir / "episodes.jsonl"
    rows = []
    if events_path.exists():
        with events_path.open(encoding="utf-8") as handle:
            rows = latest_episode_rows(json.loads(line) for line in handle if line.strip())
    completed_keys = {(str(row.get("arm")), str(row.get("game_file"))) for row in rows}
    write_tracker(run_dir, manifest, rows, status="running")

    from alfworld.agents.environment import get_environment

    config = load_config(data_dir, args.max_steps)
    reme = LegacyRemeService(run_dir, agent.model, args.port, state_dir=run_dir)
    manager = None

    def track(current: dict) -> None:
        write_tracker(run_dir, manifest, rows, status="running", current=current)

    try:
        reme.start()
        manager = get_environment("AlfredTWEnv")(config, train_eval=split)
        for index, game in enumerate(games):
            if ("legacy_reme", str(game)) in completed_keys:
                continue
            row = run_reme_episode(
                manager,
                game,
                index,
                agent,
                reme,
                args.max_steps,
                args.seed,
                progress_callback=track,
                fallback_retry_after=args.fallback_retry_after,
                fallback_disable_guidance_after=args.fallback_disable_guidance_after,
                fallback_retry_tokens=args.fallback_retry_tokens,
            )
            row["reme_controls"] = manifest["controls"]
            rows.append(row)
            append_jsonl(events_path, row)

            if len(rows) % args.cleanup_every == 0:
                try:
                    reme.delete_task_memory(args.freq_threshold, args.utility_threshold)
                    reme.checkpoint()
                except Exception as exc:
                    reme.events.append({"event": "memory_bank_cleanup_error", "error": str(exc)})

            write_progress_artifacts(run_dir, manifest, rows, agent, reme)
            print(
                f"[legacy_reme controlled] {index + 1}/{len(games)} "
                f"success={row['success']} steps={row['steps']} "
                f"fallback_recoveries={row.get('reme_fallback_recoveries', 0)}",
                flush=True,
            )
    except BaseException as exc:
        record_runner_error(run_dir, "runner_loop", exc)
        try:
            write_tracker(run_dir, manifest, rows, status="running")
        except Exception as tracker_exc:
            record_runner_error(run_dir, "error_tracker_write", tracker_exc)
        raise
    finally:
        if manager is not None and hasattr(manager, "close"):
            manager.close()
        reme.close()

    summary = summarize_three_arms(rows, agent.stats, reme)
    write_json(run_dir / "summary.json", summary)
    write_json(run_dir / "reme_service_events.json", reme.events)
    write_tracker(run_dir, manifest, rows, status="complete")
    print(json.dumps({"run_dir": str(run_dir), **summary}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
