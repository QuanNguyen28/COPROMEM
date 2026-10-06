#!/usr/bin/env python3
"""Run CoProMem and pinned legacy REmE on an existing sorted task list."""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from run_experiment import (
    ALFWORLD_REPO,
    COPROMEM_REPO,
    DATA_ROOT,
    ENV_FILE,
    RESULTS_ROOT,
    OpenRouterAgent,
    append_jsonl,
    load_config,
    np,
    paired_no_memory_score,
    run_episode,
    wsl_path,
    write_tracker,
    write_json,
)
from run_reme_experiment import LegacyRemeService, run_reme_episode, summarize_three_arms


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--max-steps", type=int, default=40)
    parser.add_argument("--port", type=int, default=8012)
    args = parser.parse_args()

    load_dotenv(ENV_FILE, override=False)
    source_manifest = json.loads((args.source_run / "manifest.json").read_text(encoding="utf-8"))
    data_dir = wsl_path(os.environ.get("ALFWORLD_DATA", str(DATA_ROOT)))
    split = source_manifest["split"]
    seed = int(source_manifest["seed"])
    os.environ["ALFWORLD_SPLIT"] = split
    config = load_config(data_dir, args.max_steps)
    games = [Path(value) for value in source_manifest["games"]]
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise SystemExit(f"OPENROUTER_API_KEY is blank. Add it to {ENV_FILE} and rerun.")

    agent = OpenRouterAgent(
        api_key=api_key,
        model=source_manifest["model"],
        max_calls=int(os.environ.get("ALFWORLD_MAX_CALLS", "1500")),
        max_usd=float(os.environ.get("ALFWORLD_MAX_USD", "5.00")),
        prompt_price_per_million=float(os.environ.get("ALFWORLD_MAX_PROMPT_PRICE_PER_M", "1.00")),
        completion_price_per_million=float(os.environ.get("ALFWORLD_MAX_COMPLETION_PRICE_PER_M", "3.00")),
    )
    token_limit = int(os.environ.get("ALFWORLD_MAX_TOKENS", "256"))
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RESULTS_ROOT / f"{run_id}-copromem-reme-sorted-1024"
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest = {
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_run": str(args.source_run),
        "alfworld_commit": source_manifest["alfworld_commit"],
        "copromem_commit": source_manifest["copromem_commit"],
        "legacy_reme_source": source_manifest["legacy_reme_source"],
        "legacy_reme_commit": source_manifest["legacy_reme_commit"],
        "model": agent.model,
        "split": split,
        "seed": seed,
        "task_count": len(games),
        "max_steps": args.max_steps,
        "max_tokens": token_limit,
        "arms": ["copromem_v2", "legacy_reme"],
        "games": [str(game) for game in games],
        "budget": {
            "max_calls": agent.max_calls,
            "max_usd": agent.max_usd,
            "max_prompt_price_per_million": agent.prompt_price,
            "max_completion_price_per_million": agent.completion_price,
        },
    }
    write_json(run_dir / "manifest.json", manifest)
    write_tracker(run_dir, manifest, [], status="running")
    if (args.source_run / "difficulty_order.json").exists():
        write_json(
            run_dir / "difficulty_order.json",
            json.loads((args.source_run / "difficulty_order.json").read_text(encoding="utf-8")),
        )

    from alfworld.agents.environment import get_environment
    from copromem.copromem_memory_module import COPROMEMMemoryModule

    rows: list[dict] = []
    source_rows = []
    source_events = args.source_run / "episodes.jsonl"
    if source_events.exists():
        for line in source_events.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                source_rows.append(value)
    events_path = run_dir / "episodes.jsonl"
    reme = LegacyRemeService(run_dir, agent.model, args.port)

    def track_step(current: dict) -> None:
        write_tracker(run_dir, manifest, rows, status="running", current=current)

    try:
        reme.start()
        random.seed(seed)
        np.random.seed(seed)
        manager = get_environment("AlfredTWEnv")(config, train_eval=split)
        memory = COPROMEMMemoryModule(api_key="", seed_default_memories=False)
        for index, game in enumerate(games):
            baseline_score = paired_no_memory_score(source_rows, game, index)
            row = run_episode(
                manager, game, "copromem_v2", index, agent, memory, args.max_steps, seed,
                progress_callback=track_step,
                baseline_score=baseline_score,
            )
            rows.append(row)
            append_jsonl(events_path, row)
            write_json(run_dir / "copromem_state.json", memory.export_state())
            write_json(run_dir / "summary.json", summarize_three_arms(rows, agent.stats, reme))
            write_tracker(run_dir, manifest, rows)
            print(
                f"[copromem_v2] {index + 1}/{len(games)} success={row['success']} "
                f"steps={row['steps']} spent_or_reserved=${agent.stats.charged_or_reserved_usd:.6f}",
                flush=True,
            )

        random.seed(seed)
        np.random.seed(seed)
        manager = get_environment("AlfredTWEnv")(config, train_eval=split)
        for index, game in enumerate(games):
            row = run_reme_episode(
                manager, game, index, agent, reme, args.max_steps, seed,
                progress_callback=track_step,
            )
            rows.append(row)
            append_jsonl(events_path, row)
            write_json(run_dir / "reme_service_events.json", reme.events)
            write_json(run_dir / "summary.json", summarize_three_arms(rows, agent.stats, reme))
            write_tracker(run_dir, manifest, rows)
            print(
                f"[legacy_reme] {index + 1}/{len(games)} success={row['success']} "
                f"steps={row['steps']} retrievals={row['retrieval'].get('memory_count', 0)} "
                f"spent_or_reserved=${agent.stats.charged_or_reserved_usd:.6f}",
                flush=True,
            )
    finally:
        reme.close()

    summary = summarize_three_arms(rows, agent.stats, reme)
    write_json(run_dir / "summary.json", summary)
    write_json(run_dir / "reme_service_events.json", reme.events)
    write_tracker(run_dir, manifest, rows, status="complete")
    print(json.dumps({"run_dir": str(run_dir), **summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
