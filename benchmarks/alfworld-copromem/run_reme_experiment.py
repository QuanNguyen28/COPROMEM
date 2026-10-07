#!/usr/bin/env python3
"""Standalone ALFWorld pilot with the pinned legacy REmE arm.

This file is intentionally outside the CoProMem repository.  It reuses the
existing ALFWorld/CoProMem pilot helpers and adapts the pinned legacy REmE
HTTP memory-service lifecycle to ALFWorld text trajectories.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from dotenv import dotenv_values, load_dotenv

from run_experiment import (
    ALFWORLD_REPO,
    COPROMEM_REPO,
    DATA_ROOT,
    ENV_FILE,
    RESULTS_ROOT,
    TASK_FAMILY_PRIORITY,
    OpenRouterAgent,
    ProviderStats,
    append_jsonl,
    check_environment,
    extract_task,
    git_dirty,
    git_head,
    load_config,
    np,
    select_games,
    select_games_by_difficulty,
    structural_descriptor,
    summarize,
    task_family,
    latest_episode_rows,
    wsl_path,
    write_tracker,
    write_json,
)


EXPERIMENT_DIR = Path(__file__).resolve().parent
WORKSPACE = COPROMEM_REPO.parent
DEFAULT_REME_SOURCE = WORKSPACE / "reme-upstream-fixed-dynamic"
DEFAULT_REME_PYTHON = "/home/dminh110806/reme-env-wsl/bin/python"
# The two paired retry cases were the unique failures in the original
# 30-step pilot.  The later 60-step retry contains one failure and one success.
DEFAULT_PREVIOUS_RUN = RESULTS_ROOT / "20261001T165132Z" / "episodes.jsonl"


class LegacyRemeService:
    """Run and call the pinned legacy REmE HTTP service."""

    def __init__(
        self,
        run_dir: Path,
        model: str,
        port: int,
        *,
        state_dir: Path | None = None,
        workspace_id: str | None = None,
        seed_snapshot: Path | None = None,
    ) -> None:
        self.run_dir = run_dir
        self.state_dir = state_dir or run_dir
        self.model = model
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self.workspace_id = workspace_id or os.environ.get(
            "ALFWORLD_REME_WORKSPACE_ID", "alfworld-legacy-pilot"
        )
        configured_seed = os.environ.get("ALFWORLD_REME_SEED_SNAPSHOT", "").strip()
        self.seed_snapshot = seed_snapshot or (Path(configured_seed) if configured_seed else None)
        self.snapshot_dir = self.state_dir / "reme-task-memory"
        self.snapshot_path = self.snapshot_dir / f"{self.workspace_id}.jsonl"
        self.source = Path(
            os.environ.get("COPROMEM_REME_SOURCE", str(DEFAULT_REME_SOURCE))
        )
        self.python = os.environ.get("COPROMEM_REME_PYTHON", DEFAULT_REME_PYTHON)
        self.process: subprocess.Popen[bytes] | None = None
        self.log_handle: Any = None
        self.events: list[dict[str, Any]] = []

    def _service_environment(self) -> dict[str, str]:
        values = dotenv_values(ENV_FILE)
        key = os.environ.get("OPENROUTER_API_KEY", "").strip() or str(
            values.get("OPENROUTER_API_KEY", "") or ""
        ).strip()
        if not key:
            raise RuntimeError(f"OPENROUTER_API_KEY is blank in {ENV_FILE}")
        base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or str(
            values.get("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
        ).strip()
        environment = os.environ.copy()
        environment.update(
            {
                "FLOW_LLM_API_KEY": key,
                "FLOW_LLM_BASE_URL": base_url,
                "FLOW_EMBEDDING_API_KEY": key,
                "FLOW_EMBEDDING_BASE_URL": base_url,
                "OPENAI_API_KEY": key,
                "OPENAI_BASE_URL": base_url,
                "PYTHONUNBUFFERED": "1",
                "TOKENIZERS_PARALLELISM": "false",
            }
        )
        return environment

    def start(self) -> None:
        log_path = self.run_dir / "reme-service.log"
        self.log_handle = log_path.open("wb")
        command = [
            self.python,
            "-m",
            "reme_ai.main",
            "backend=http",
            f"http.port={self.port}",
            f"llm.default.model_name={self.model}",
            f'llm.default.params={{"temperature":0,"max_tokens":{os.environ.get("ALFWORLD_REME_MAX_TOKENS", os.environ.get("ALFWORLD_MAX_TOKENS", "1024"))}}}',
            "embedding_model.default.model_name=openai/text-embedding-3-small",
            'embedding_model.default.params={"dimensions":1536}',
            "vector_store.default.backend=memory",
        ]
        self.process = subprocess.Popen(
            command,
            cwd=str(self.source),
            env=self._service_environment(),
            stdout=self.log_handle,
            stderr=subprocess.STDOUT,
        )
        deadline = time.time() + 90
        while time.time() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(
                    f"legacy REmE service exited with code {self.process.returncode}; "
                    f"see {log_path}"
                )
            try:
                request = urllib.request.Request(f"{self.base_url}/docs", method="GET")
                with urllib.request.urlopen(request, timeout=3) as response:
                    if response.status == 200:
                        self.events.append({"event": "service_ready", "port": self.port})
                        self.restore_snapshot()
                        return
            except (urllib.error.URLError, TimeoutError):
                time.sleep(1)
        raise RuntimeError(f"legacy REmE service did not become ready; see {log_path}")

    def close(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.log_handle is not None:
            self.log_handle.close()

    def post(self, path: str, payload: dict[str, Any], timeout: int = 240) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                value = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")[:1200]
            raise RuntimeError(f"REmE HTTP {exc.code} at {path}: {raw}") from None
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise RuntimeError(f"REmE transport failure at {path}: {exc}") from None
        if not isinstance(value, dict):
            raise RuntimeError(f"REmE returned non-object at {path}")
        return value

    @staticmethod
    def _validate_snapshot(path: Path) -> int:
        """Validate an upstream JSONL vector-store dump before loading it."""
        count = 0
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, 1):
                    if not line.strip():
                        continue
                    value = json.loads(line)
                    if not isinstance(value, dict):
                        raise ValueError(f"line {line_number} is not an object")
                    count += 1
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"invalid REmE snapshot {path}: {exc}") from None
        return count

    def restore_snapshot(self) -> dict[str, Any]:
        """Restore the run-local bank, or an explicitly configured seed bank."""
        snapshot = self.snapshot_path if self.snapshot_path.is_file() else None
        snapshot_dir = self.snapshot_dir
        seeded = False
        if snapshot is None and self.seed_snapshot is not None:
            seeded = True
            if self.seed_snapshot.is_dir():
                snapshot_dir = self.seed_snapshot
                snapshot = snapshot_dir / f"{self.workspace_id}.jsonl"
            else:
                snapshot = self.seed_snapshot
                snapshot_dir = snapshot.parent
                expected_name = f"{self.workspace_id}.jsonl"
                if snapshot.name != expected_name:
                    raise RuntimeError(
                        "configured REmE seed snapshot must be a dump directory or "
                        f"a file named {expected_name}: {snapshot}"
                    )
        if snapshot is None:
            self.snapshot_dir.mkdir(parents=True, exist_ok=True)
            self.snapshot_path.write_text("", encoding="utf-8")
            response = self.post(
                "/vector_store",
                {
                    "workspace_id": self.workspace_id,
                    "action": "load",
                    "path": str(self.snapshot_dir),
                },
            )
            event = {
                "event": "memory_bank_started_empty",
                "workspace_id": self.workspace_id,
                "snapshot": str(self.snapshot_path),
            }
            self.events.append(event)
            return {"event": event, "response": response}
        if not snapshot.is_file():
            raise RuntimeError(f"configured REmE seed snapshot does not exist: {snapshot}")
        memory_count = self._validate_snapshot(snapshot)
        response = self.post(
            "/vector_store",
            {
                "workspace_id": self.workspace_id,
                "action": "load",
                "path": str(snapshot_dir),
            },
        )
        event = {
            "event": "memory_bank_restored",
            "workspace_id": self.workspace_id,
            "snapshot": str(snapshot),
            "memory_count": memory_count,
            "seeded": seeded,
        }
        self.events.append(event)
        if seeded:
            self.checkpoint()
        return {"event": event, "response": response}

    def checkpoint(self) -> dict[str, Any]:
        """Atomically persist the in-memory upstream bank after an episode."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        temporary_dir = self.state_dir / (
            f".reme-task-memory-{os.getpid()}-{time.time_ns()}.tmp"
        )
        temporary_path = temporary_dir / f"{self.workspace_id}.jsonl"
        if temporary_dir.exists():
            raise RuntimeError(f"stale REmE checkpoint directory exists: {temporary_dir}")
        response = self.post(
            "/vector_store",
            {
                "workspace_id": self.workspace_id,
                "action": "dump",
                "path": str(temporary_dir),
            },
        )
        if not temporary_path.is_file():
            # The pinned memory backend returns an empty result, without a file,
            # when no memory has been inserted yet. Preserve that valid state.
            temporary_dir.mkdir(parents=True, exist_ok=True)
            temporary_path.write_text("", encoding="utf-8")
        memory_count = self._validate_snapshot(temporary_path)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        os.replace(temporary_path, self.snapshot_path)
        temporary_dir.rmdir()
        event = {
            "event": "memory_bank_checkpointed",
            "workspace_id": self.workspace_id,
            "snapshot": str(self.snapshot_path),
            "memory_count": memory_count,
        }
        self.events.append(event)
        return {"event": event, "response": response}

    def recover_snapshot_from_rows(self, rows: list[dict[str, Any]]) -> int:
        """Recover pre-patch summary memories without replaying model calls.

        Historical episode rows contain the exact upstream TaskMemory objects
        returned by ``summary_task_memory``. They can seed the vector-store
        loader, but only when the recorded update metadata is unambiguous.
        """
        if self.snapshot_path.is_file():
            return self._validate_snapshot(self.snapshot_path)
        memories: dict[str, dict[str, Any]] = {}
        for row in rows:
            if row.get("arm") != "legacy_reme":
                continue
            metadata_sources = [
                ((row.get("reme_summary") or {}).get("response") or {}).get("metadata") or {},
                ((row.get("reme_feedback") or {}).get("response") or {}).get("metadata") or {},
            ]
            for metadata in metadata_sources:
                update_result = metadata.get("update_result") or {}
                deleted_count = int(update_result.get("deleted_count", 0) or 0)
                deleted_ids = metadata.get("deleted_memory_ids") or []
                if deleted_count and len(deleted_ids) != deleted_count:
                    raise RuntimeError(
                        "cannot recover historical REmE bank: update deletion IDs are absent"
                    )
                for memory_id in deleted_ids:
                    memories.pop(str(memory_id), None)
                for memory in metadata.get("memory_list") or []:
                    if not isinstance(memory, dict) or not memory.get("memory_id"):
                        raise RuntimeError(
                            "cannot recover historical REmE bank: invalid memory record"
                        )
                    memories[str(memory["memory_id"])] = memory
        if not memories:
            return 0
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.snapshot_path.with_suffix(self.snapshot_path.suffix + ".recovering")
        with temporary.open("w", encoding="utf-8") as handle:
            for memory in memories.values():
                handle.write(json.dumps(memory, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.snapshot_path)
        event = {
            "event": "memory_bank_recovered_from_episode_rows",
            "workspace_id": self.workspace_id,
            "snapshot": str(self.snapshot_path),
            "memory_count": len(memories),
        }
        self.events.append(event)
        return len(memories)

    def retrieve(self, query: str) -> dict[str, Any]:
        response = self.post(
            "/retrieve_task_memory",
            {
                "workspace_id": self.workspace_id,
                "query": query,
                "enable_llm_rerank": False,
                "enable_score_filter": False,
                "enable_utility_rerank": True,
                "utility_weight": float(os.environ.get("ALFWORLD_REME_UTILITY_WEIGHT", "0.35")),
                "top_k": 5,
                "enable_llm_rewrite": False,
            },
        )
        metadata = response.get("metadata") or {}
        memory_list = metadata.get("memory_list", []) if isinstance(metadata, dict) else []
        answer = response.get("answer", "")
        return {
            "answer": answer if isinstance(answer, str) else str(answer),
            "memory_list": memory_list if isinstance(memory_list, list) else [],
            "response": response,
        }

    def summarize_trajectory(
        self, task_id: str, messages: list[dict[str, str]], success: bool
    ) -> dict[str, Any]:
        response = self.post(
            "/summary_task_memory",
            {
                "workspace_id": self.workspace_id,
                "trajectories": [
                    {"task_id": task_id, "messages": messages, "score": 1.0 if success else 0.0}
                ],
                "success_threshold": 1.0,
                "enable_soft_comparison": True,
                "validation_threshold": 0.5,
            },
        )
        metadata = response.get("metadata") or {}
        memory_list = metadata.get("memory_list", []) if isinstance(metadata, dict) else []
        return {
            "response": response,
            "memory_count": len(memory_list) if isinstance(memory_list, list) else 0,
        }

    def record_retrieved(self, memory_list: list[Any], success: bool) -> dict[str, Any] | None:
        if not memory_list:
            return None
        return self.post(
            "/record_task_memory",
            {
                "workspace_id": self.workspace_id,
                "memory_dicts": memory_list,
                "update_utility": bool(success),
            },
        )

    def delete_task_memory(
        self, freq_threshold: int = 5, utility_threshold: float = 0.5
    ) -> dict[str, Any]:
        """Delete frequently recalled memories with a low success ratio."""
        response = self.post(
            "/delete_task_memory",
            {
                "workspace_id": self.workspace_id,
                "freq_threshold": int(freq_threshold),
                "utility_threshold": float(utility_threshold),
            },
        )
        self.events.append(
            {
                "event": "memory_bank_cleaned",
                "workspace_id": self.workspace_id,
                "freq_threshold": int(freq_threshold),
                "utility_threshold": float(utility_threshold),
                "response": response,
            }
        )
        return response


def previous_failed_games(path: Path, count: int) -> list[Path]:
    if not path.exists():
        return []
    found: list[Path] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        game_file = row.get("game_file")
        if row.get("success") or not game_file or game_file in seen:
            continue
        seen.add(game_file)
        found.append(Path(game_file))
        if len(found) >= count:
            break
    return found


def trajectory_messages(task: str, initial_observation: str, trajectory: list[dict[str, Any]]) -> list[dict[str, str]]:
    messages = [
        {"role": "user", "content": f"Task: {task}\nInitial observation: {initial_observation}"}
    ]
    for row in trajectory:
        messages.append({"role": "assistant", "content": row["action"]})
        messages.append({"role": "user", "content": f"Observation: {row['observation']}"})
    return messages


def run_reme_episode(
    manager: Any,
    game_file: Path,
    episode_index: int,
    agent: OpenRouterAgent,
    reme: LegacyRemeService,
    max_steps: int,
    seed: int,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    fallback_retry_after: int = 0,
    fallback_disable_guidance_after: int = 0,
    fallback_retry_tokens: int = 256,
) -> dict[str, Any]:
    family = task_family(game_file)
    manager.game_files = [str(game_file)]
    manager.num_games = 1
    env = manager.init_env(batch_size=1)
    started = time.time()
    trajectory: list[dict[str, Any]] = []
    retrieval: dict[str, Any] = {}
    task = ""
    initial_observation = ""
    memory_list: list[Any] = []
    service_errors: list[str] = []
    try:
        observations, infos = env.reset()
        initial_observation = str(observations[0])
        observation = initial_observation
        task = extract_task(observation)
        if progress_callback is not None:
            progress_callback({
                "arm": "legacy_reme",
                "episode_index": episode_index,
                "task_family": family,
                "task": task,
                "step": 1,
                "max_steps": max_steps,
                "phase": "waiting_for_model",
            })
        task_id = str(game_file.relative_to(Path(os.environ["ALFWORLD_DATA"])))
        try:
            retrieved = reme.retrieve(task)
            memory_list = retrieved["memory_list"]
            guidance = retrieved["answer"]
            retrieval = {
                "memory_count": len(memory_list),
                "guidance": guidance,
                "source": "pinned_legacy_reme_task_memory_service",
                "utility_rerank": True,
                "utility_weight": float(os.environ.get("ALFWORLD_REME_UTILITY_WEIGHT", "0.35")),
            }
        except RuntimeError as exc:
            service_errors.append(str(exc))
            guidance = ""

        won = False
        done = False
        fallback_streak = 0
        fallback_recoveries = 0
        for step in range(max_steps):
            if progress_callback is not None:
                progress_callback({
                    "arm": "legacy_reme",
                    "episode_index": episode_index,
                    "task_family": family,
                    "task": task,
                    "step": step + 1,
                    "max_steps": max_steps,
                    "phase": "waiting_for_model",
                })
            admissible = [str(item) for item in infos["admissible_commands"][0]]
            guidance_for_call = (
                ""
                if fallback_disable_guidance_after > 0
                and fallback_streak >= fallback_disable_guidance_after
                else guidance
            )
            action, provider = agent.choose_action(
                task,
                observation,
                admissible,
                [{"action": row["action"], "observation": row["observation"]} for row in trajectory],
                guidance_for_call,
                seed + episode_index * 1000 + step,
            )
            parse_mode = str(provider.get("parse_mode", ""))
            is_fallback = parse_mode in {"safe_fallback", "first_fallback"}
            if is_fallback:
                fallback_streak += 1
                if (
                    fallback_retry_after > 0
                    and fallback_streak >= fallback_retry_after
                ):
                    recovery_action, recovery_provider = agent.choose_action(
                        task,
                        observation,
                        admissible,
                        [{"action": row["action"], "observation": row["observation"]} for row in trajectory],
                        "",
                        seed + episode_index * 1000 + step + 500_000,
                        guidance_label="REME FALLBACK RECOVERY",
                        max_tokens_override=fallback_retry_tokens,
                    )
                    provider["fallback_recovery"] = recovery_provider
                    provider["fallback_recovery_attempted"] = True
                    recovery_mode = str(recovery_provider.get("parse_mode", ""))
                    if recovery_mode not in {"safe_fallback", "first_fallback"}:
                        action = recovery_action
                        provider["fallback_recovery_used"] = True
                        provider["parse_mode"] = f"recovery_{recovery_mode}"
                        fallback_recoveries += 1
                        fallback_streak = 0
            else:
                fallback_streak = 0
            next_obs, _scores, dones, infos = env.step([action])
            observation = str(next_obs[0])
            done = bool(dones[0])
            won = bool((infos.get("won") or [False])[0])
            trajectory.append(
                {
                    "step": step + 1,
                    "action": action,
                    "observation": observation,
                    "done": done,
                    "won": won,
                    "provider": provider,
                }
            )
            if progress_callback is not None:
                progress_callback({
                    "arm": "legacy_reme",
                    "episode_index": episode_index,
                    "task_family": family,
                    "task": task,
                    "step": step + 1,
                    "max_steps": max_steps,
                    "phase": "environment_step_complete",
                    "action": action,
                })
            if done or won:
                break

        messages = trajectory_messages(task, initial_observation, trajectory)
        reme_summary: dict[str, Any] = {"memory_count": 0}
        reme_feedback: dict[str, Any] = {
            "attempted": bool(memory_list),
            "updated": False,
            "retrieved_memory_count": len(memory_list),
        }
        try:
            reme_summary = reme.summarize_trajectory(task_id, messages, won)
        except RuntimeError as exc:
            service_errors.append(str(exc))
        if memory_list:
            try:
                feedback_response = reme.record_retrieved(memory_list, won)
                reme_feedback.update({"updated": True, "response": feedback_response})
            except RuntimeError as exc:
                reme_feedback["error"] = str(exc)
                service_errors.append(str(exc))
        try:
            reme_checkpoint = reme.checkpoint()
        except RuntimeError as exc:
            reme_checkpoint = {"persisted": False, "error": str(exc)}
            service_errors.append(str(exc))
        return {
            "arm": "legacy_reme",
            "episode_index": episode_index,
            "task_id": task_id,
            "task_family": family,
            "task": task,
            "game_file": str(game_file),
            "success": won,
            "done": done,
            "steps": len(trajectory),
            "duration_seconds": round(time.time() - started, 3),
            "retrieval": retrieval,
            "reme_summary": reme_summary,
            "reme_feedback": reme_feedback,
            "reme_checkpoint": reme_checkpoint,
            "service_errors": service_errors,
            "reme_fallback_recoveries": fallback_recoveries,
            "trajectory": trajectory,
        }
    finally:
        env.close()


def summarize_three_arms(rows: list[dict[str, Any]], stats: ProviderStats, service: LegacyRemeService) -> dict[str, Any]:
    rows = latest_episode_rows(rows)
    base = summarize(rows, stats)
    arms: dict[str, dict[str, Any]] = base["arms"]
    reme_rows = [row for row in rows if row["arm"] == "legacy_reme"]
    if reme_rows:
        wins = sum(bool(row["success"]) for row in reme_rows)
        arms["legacy_reme"] = {
            "tasks": len(reme_rows),
            "successes": wins,
            "success_rate": wins / len(reme_rows),
            "average_steps": sum(row["steps"] for row in reme_rows) / len(reme_rows),
            "retrieval_hits": sum(bool(row.get("retrieval", {}).get("memory_count")) for row in reme_rows),
        }
        if "no_memory" in arms:
            base["legacy_reme_minus_no_memory_success_rate"] = (
                arms["legacy_reme"]["success_rate"] - arms["no_memory"]["success_rate"]
            )
    base["arms"] = arms
    base["legacy_reme_service"] = {
        "source": str(service.source),
        "source_commit": git_head(service.source),
        "python": service.python,
        "port": service.port,
        "events": service.events,
    }
    return base


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--tasks", type=int, default=2)
    parser.add_argument("--max-steps", type=int, default=60)
    parser.add_argument("--seed", type=int, default=1108)
    parser.add_argument("--port", type=int, default=8012)
    parser.add_argument("--from-run", type=Path, default=DEFAULT_PREVIOUS_RUN)
    parser.add_argument("--difficulty-sort", action="store_true")
    args = parser.parse_args()

    load_dotenv(ENV_FILE, override=False)
    data_dir = wsl_path(os.environ.get("ALFWORLD_DATA", str(DATA_ROOT)))
    split = os.environ.get("ALFWORLD_SPLIT", "eval_out_of_distribution")
    os.environ["ALFWORLD_SPLIT"] = split
    if args.tasks < 1 or args.max_steps < 1:
        raise ValueError("tasks and max steps must be positive")

    random.seed(args.seed)
    np.random.seed(args.seed)
    config = load_config(data_dir, args.max_steps)
    difficulty_rows = None
    if args.difficulty_sort:
        games, difficulty_rows = select_games_by_difficulty(data_dir, split, args.tasks)
    else:
        games = previous_failed_games(args.from_run, args.tasks)
        if len(games) < args.tasks:
            games = select_games(data_dir, split, args.tasks)
    if args.check:
        print(json.dumps(check_environment(config, games), indent=2))
        return 0

    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise SystemExit(f"OPENROUTER_API_KEY is blank. Add it to {ENV_FILE} and rerun.")
    agent = OpenRouterAgent(
        api_key=api_key,
        model=os.environ.get("ALFWORLD_MODEL", "google/gemini-2.5-flash"),
        max_calls=int(os.environ.get("ALFWORLD_MAX_CALLS", "360")),
        max_usd=float(os.environ.get("ALFWORLD_MAX_USD", "1.00")),
        prompt_price_per_million=float(os.environ.get("ALFWORLD_MAX_PROMPT_PRICE_PER_M", "1.00")),
        completion_price_per_million=float(os.environ.get("ALFWORLD_MAX_COMPLETION_PRICE_PER_M", "3.00")),
    )

    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    run_dir = RESULTS_ROOT / run_id
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
        "arms": ["no_memory", "copromem_v2", "legacy_reme"],
        "from_run": str(args.from_run),
        "difficulty_sort": args.difficulty_sort,
        "games": [str(game) for game in games],
        "budget": {
            "max_calls": agent.max_calls,
            "max_usd": agent.max_usd,
            "max_prompt_price_per_million": agent.prompt_price,
            "max_completion_price_per_million": agent.completion_price,
        },
    }
    if difficulty_rows is not None:
        write_json(run_dir / "difficulty_order.json", difficulty_rows)
    write_json(run_dir / "manifest.json", manifest)
    write_tracker(run_dir, manifest, [], status="running")

    from alfworld.agents.environment import get_environment

    reme = LegacyRemeService(run_dir, agent.model, args.port)
    all_rows: list[dict[str, Any]] = []
    events_path = run_dir / "episodes.jsonl"

    def track_step(current: dict[str, Any]) -> None:
        write_tracker(run_dir, manifest, all_rows, status="running", current=current)

    try:
        reme.start()
        for arm in ("no_memory", "copromem_v2"):
            random.seed(args.seed)
            np.random.seed(args.seed)
            manager = get_environment("AlfredTWEnv")(config, train_eval=split)
            memory = (
                __import__("copromem.copromem_memory_module", fromlist=["COPROMEMMemoryModule"])
                .COPROMEMMemoryModule(api_key="", seed_default_memories=False)
                if arm == "copromem_v2" else None
            )
            for index, game in enumerate(games):
                from run_experiment import run_episode

                baseline_score = (
                    next(
                        (
                            float(bool(previous.get("success")))
                            for previous in reversed(all_rows)
                            if previous.get("arm") == "no_memory"
                            and int(previous.get("episode_index", -1)) == index
                        ),
                        None,
                    )
                    if arm == "copromem_v2" else None
                )
                row = run_episode(
                    manager, game, arm, index, agent, memory, args.max_steps, args.seed,
                    progress_callback=track_step,
                    baseline_score=baseline_score,
                )
                all_rows.append(row)
                append_jsonl(events_path, row)
                write_json(run_dir / "summary.json", summarize_three_arms(all_rows, agent.stats, reme))
                write_tracker(run_dir, manifest, all_rows)
                print(
                    f"[{arm}] {index + 1}/{len(games)} {row['task_family']} "
                    f"success={row['success']} steps={row['steps']} "
                    f"spent_or_reserved=${agent.stats.charged_or_reserved_usd:.6f}",
                    flush=True,
                )

        random.seed(args.seed)
        np.random.seed(args.seed)
        manager = get_environment("AlfredTWEnv")(config, train_eval=split)
        for index, game in enumerate(games):
            row = run_reme_episode(
                manager, game, index, agent, reme, args.max_steps, args.seed,
                progress_callback=track_step,
            )
            all_rows.append(row)
            append_jsonl(events_path, row)
            write_json(run_dir / "summary.json", summarize_three_arms(all_rows, agent.stats, reme))
            write_json(run_dir / "reme_service_events.json", reme.events)
            write_tracker(run_dir, manifest, all_rows)
            print(
                f"[legacy_reme] {index + 1}/{len(games)} {row['task_family']} "
                f"success={row['success']} steps={row['steps']} "
                f"retrievals={row['retrieval'].get('memory_count', 0)} "
                f"spent_or_reserved=${agent.stats.charged_or_reserved_usd:.6f}",
                flush=True,
            )
    finally:
        reme.close()

    summary = summarize_three_arms(all_rows, agent.stats, reme)
    write_json(run_dir / "summary.json", summary)
    write_json(run_dir / "reme_service_events.json", reme.events)
    write_tracker(run_dir, manifest, all_rows, status="complete")
    print(json.dumps({"run_dir": str(run_dir), **summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
