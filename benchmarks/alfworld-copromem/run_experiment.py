#!/usr/bin/env python3
"""Standalone ALFWorld x CoProMem paired pilot.

This runner intentionally lives outside the CoProMem repository.  It imports
CoProMem through its public API and does not patch either source tree.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import random
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np
import yaml
from dotenv import load_dotenv


EXPERIMENT_DIR = Path(__file__).resolve().parent
COPROMEM_REPO = EXPERIMENT_DIR.parents[1]
WORKSPACE = COPROMEM_REPO.parent
ALFWORLD_REPO = COPROMEM_REPO / "benchmarks" / "alfworld"
DATA_ROOT = WORKSPACE / "alfworld-data"
ENV_FILE = COPROMEM_REPO / ".env"
RESULTS_ROOT = COPROMEM_REPO / "benchmarks" / "results"


def read_openrouter_payload(request: urllib.request.Request) -> dict[str, Any]:
    """Read one OpenRouter response with both idle and total request deadlines."""
    total_timeout = float(os.environ.get("ALFWORLD_REQUEST_TOTAL_TIMEOUT", "90"))
    if total_timeout <= 0:
        raise ValueError("ALFWORLD_REQUEST_TOTAL_TIMEOUT must be positive")

    alarm_supported = hasattr(signal, "SIGALRM") and hasattr(signal, "setitimer")
    previous_handler = None
    previous_timer = (0.0, 0.0)
    if alarm_supported:
        previous_handler = signal.getsignal(signal.SIGALRM)
        previous_timer = signal.getitimer(signal.ITIMER_REAL)

        def raise_total_timeout(_signum: int, _frame: Any) -> None:
            raise TimeoutError(
                f"OpenRouter response exceeded total timeout of {total_timeout:.0f}s"
            )

        signal.signal(signal.SIGALRM, raise_total_timeout)
        signal.setitimer(signal.ITIMER_REAL, total_timeout)

    try:
        with urllib.request.urlopen(request, timeout=total_timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    finally:
        if alarm_supported:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)
            if previous_timer[0] > 0:
                signal.setitimer(signal.ITIMER_REAL, *previous_timer)

sys.path.insert(0, str(COPROMEM_REPO / "src"))

from copromem.copromem_memory_module import COPROMEMMemoryModule  # noqa: E402
from copromem.learning import ActionObservation  # noqa: E402
from copromem_adapter import ADAPTER_VERSION, AlfworldCopromemController  # noqa: E402


TASK_FAMILY_PRIORITY = (
    "pick_and_place_simple",
    "pick_clean_then_place_in_recep",
    "pick_heat_then_place_in_recep",
    "pick_cool_then_place_in_recep",
    "look_at_obj_in_light",
    "pick_two_obj_and_place",
)


@dataclass
class ProviderStats:
    calls: int = 0
    attempts: int = 0
    retained_failed_reservations_usd: float = 0.0
    charged_or_reserved_usd: float = 0.0


class BudgetStop(RuntimeError):
    pass


class OpenRouterAgent:
    def __init__(
        self,
        api_key: str,
        model: str,
        max_calls: int,
        max_usd: float,
        prompt_price_per_million: float,
        completion_price_per_million: float,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.max_calls = max_calls
        self.max_usd = max_usd
        self.prompt_price = prompt_price_per_million
        self.completion_price = completion_price_per_million
        self.stats = ProviderStats()

    def _reserve(self, system: str, user: str, max_tokens: int) -> float:
        if self.stats.attempts >= self.max_calls:
            raise BudgetStop(f"provider attempt cap reached ({self.max_calls})")
        prompt_bound = len((system + user).encode("utf-8")) + 1024
        bound = (
            prompt_bound * self.prompt_price
            + max_tokens * self.completion_price
        ) / 1_000_000
        if self.stats.charged_or_reserved_usd + bound > self.max_usd:
            raise BudgetStop(
                f"provider budget cap reached (${self.max_usd:.4f}); "
                f"next reserved bound would be ${bound:.6f}"
            )
        self.stats.attempts += 1
        self.stats.charged_or_reserved_usd += bound
        return bound

    def choose_action(
        self,
        task: str,
        observation: str,
        admissible: list[str],
        history: list[dict[str, str]],
        memory_guidance: str,
        seed: int,
        guidance_label: str = "COPROMEM GUIDANCE",
        max_tokens_override: int | None = None,
    ) -> tuple[str, dict[str, Any]]:
        system = (
            "You control an ALFWorld text household environment. Choose exactly one "
            "action from the admissible-action list on every turn. Reply with only the "
            "exact action text: no JSON, labels, reasoning, markdown, or punctuation. "
            "Track objects, receptacles, inventory, and required transformations. Avoid "
            "repeating an action that just failed unless the state has changed."
        )
        recent = history[-8:]
        guidance = memory_guidance.strip() or "(none)"
        user = (
            f"TASK:\n{task}\n\n"
            f"{guidance_label}:\n{guidance}\n\n"
            f"RECENT TRAJECTORY:\n{json.dumps(recent, ensure_ascii=False)}\n\n"
            f"CURRENT OBSERVATION:\n{observation}\n\n"
            "ADMISSIBLE ACTIONS:\n- " + "\n- ".join(admissible)
        )
        max_tokens = int(
            max_tokens_override
            if max_tokens_override is not None
            else os.environ.get("ALFWORLD_MAX_TOKENS", "256")
        )
        body = {
            "model": self.model,
            "temperature": 0,
            "seed": seed,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "provider": {
                "allow_fallbacks": False,
                "max_price": {
                    "prompt": self.prompt_price,
                    "completion": self.completion_price,
                },
            },
        }
        last_error = ""
        for attempt_index in range(3):
            reservation = self._reserve(system, user, max_tokens)
            request = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "X-Title": "CoProMem ALFWorld paired pilot",
                },
                method="POST",
            )
            try:
                payload = read_openrouter_payload(request)
                usage = payload.get("usage") or {}
                actual = usage.get("cost")
                actual_cost = reservation if actual is None else float(actual)
                self.stats.charged_or_reserved_usd += actual_cost - reservation
                self.stats.calls += 1
                if actual_cost > reservation + 1e-9:
                    raise BudgetStop(
                        "provider cost exceeded the reserved price bound; stopping"
                    )
                choice = (payload.get("choices") or [{}])[0]
                content = (choice.get("message") or {}).get("content", "")
                if isinstance(content, list):
                    content = "".join(
                        part.get("text", "")
                        for part in content
                        if isinstance(part, dict)
                    )
                action, parse_mode = parse_action(str(content), admissible)
                return action, {
                    "raw_choice": str(content),
                    "parse_mode": parse_mode,
                    "model": payload.get("model", self.model),
                    "provider": payload.get("provider"),
                    "response_id": payload.get("id"),
                    "usage": usage,
                    "settled_cost_usd": actual_cost,
                }
            except urllib.error.HTTPError as exc:
                self.stats.retained_failed_reservations_usd += reservation
                raw = exc.read().decode("utf-8", errors="replace")[:1000]
                last_error = f"OpenRouter HTTP {exc.code}: {raw}"
                if exc.code not in {429, 502, 503, 504} or attempt_index == 2:
                    raise RuntimeError(last_error) from None
                time.sleep(1.5 * (attempt_index + 1))
            except (
                urllib.error.URLError,
                http.client.IncompleteRead,
                TimeoutError,
                ValueError,
            ) as exc:
                self.stats.retained_failed_reservations_usd += reservation
                last_error = f"OpenRouter transport failure: {exc}"
                if attempt_index == 2:
                    raise RuntimeError(last_error) from None
                time.sleep(1.5 * (attempt_index + 1))
        raise RuntimeError(last_error or "OpenRouter call failed")


def parse_action(raw: str, admissible: list[str]) -> tuple[str, str]:
    cleaned = raw.strip().strip("`").strip()
    cleaned = re.sub(r"^(?:action\s*:\s*)", "", cleaned, flags=re.I)
    cleaned = cleaned.strip().strip('"\'').rstrip(".")
    by_lower = {item.lower(): item for item in admissible}
    if cleaned.lower() in by_lower:
        return by_lower[cleaned.lower()], "exact"
    lines = [line.strip().strip('"\'').rstrip(".") for line in cleaned.splitlines()]
    matches = [by_lower[line.lower()] for line in lines if line.lower() in by_lower]
    if len(set(matches)) == 1:
        return matches[0], "exact_line"
    contained = [item for item in admissible if item.lower() in cleaned.lower()]
    if len(contained) == 1:
        return contained[0], "unique_substring"
    for safe in ("look", "inventory"):
        if safe in by_lower:
            return by_lower[safe], "safe_fallback"
    return admissible[0], "first_fallback"


def wsl_path(raw: str) -> Path:
    match = re.match(r"^([A-Za-z]):[\\/](.*)$", raw)
    if not match:
        return Path(raw)
    drive, rest = match.groups()
    return Path("/mnt") / drive.lower() / Path(rest.replace("\\", "/"))


def git_head(path: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
    ).strip()


def git_dirty(path: Path) -> bool:
    output = subprocess.check_output(
        [
            "git", "-c", "core.filemode=false", "-c", "core.autocrlf=true",
            "-C", str(path), "status", "--short",
        ],
        text=True,
    )
    return bool(output.strip())


def load_config(data_dir: Path, max_steps: int) -> dict[str, Any]:
    os.environ["ALFWORLD_DATA"] = str(data_dir)
    config_path = ALFWORLD_REPO / "configs" / "base_config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["dataset"]["num_eval_games"] = -1
    config["env"]["type"] = "AlfredTWEnv"
    config["env"]["domain_randomization"] = False
    config["general"]["training_method"] = "dagger"
    config["dagger"]["training"]["max_nb_steps_per_episode"] = max_steps
    return config


def task_family(game_file: Path) -> str:
    traj = game_file.with_name("traj_data.json")
    if traj.exists():
        value = json.loads(traj.read_text(encoding="utf-8")).get("task_type")
        if value:
            return str(value)
    return game_file.parents[1].name.split("-", 1)[0]


def select_games(data_dir: Path, split_name: str, count: int) -> list[Path]:
    split_folder = {
        "eval_out_of_distribution": "valid_unseen",
        "eval_in_distribution": "valid_seen",
    }.get(split_name)
    if split_folder is None:
        raise ValueError("split must be eval_out_of_distribution or eval_in_distribution")
    root = data_dir / "json_2.1.1" / split_folder
    grouped: dict[str, list[Path]] = {}
    for game in sorted(root.rglob("game.tw-pddl")):
        try:
            game_meta = json.loads(game.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not game_meta.get("solvable", False):
            continue
        grouped.setdefault(task_family(game), []).append(game)
    available = [family for family in TASK_FAMILY_PRIORITY if grouped.get(family)]
    if not available:
        raise RuntimeError(f"no solvable ALFWorld games found under {root}")

    # Transfer needs repeated task families. Prefer pairs, then fill any remainder.
    family_count = min(len(available), max(1, count // 2))
    selected_families = available[:family_count]
    selected: list[Path] = []
    round_index = 0
    while len(selected) < count:
        made_progress = False
        for family in selected_families:
            games = grouped[family]
            if round_index < len(games) and len(selected) < count:
                selected.append(games[round_index])
                made_progress = True
        if not made_progress:
            break
        round_index += 1
    if len(selected) < count:
        raise RuntimeError(f"requested {count} tasks but selected only {len(selected)}")
    return selected


def difficulty_order(data_dir: Path, split_name: str) -> list[dict[str, Any]]:
    split_folder = {
        "eval_out_of_distribution": "valid_unseen",
        "eval_in_distribution": "valid_seen",
    }.get(split_name)
    if split_folder is None:
        raise ValueError("split must be eval_out_of_distribution or eval_in_distribution")
    root = data_dir / "json_2.1.1" / split_folder
    ordered: list[dict[str, Any]] = []
    for game in sorted(root.rglob("game.tw-pddl")):
        try:
            game_meta = json.loads(game.read_text(encoding="utf-8"))
            if not game_meta.get("solvable", False):
                continue
            traj = json.loads(game.with_name("traj_data.json").read_text(encoding="utf-8"))
            low_actions = traj.get("plan", {}).get("low_actions", [])
            high_actions = traj.get("plan", {}).get("high_pddl", [])
            ordered.append(
                {
                    "game_file": str(game),
                    "task_family": str(traj.get("task_type", task_family(game))),
                    "expert_steps": len(low_actions),
                    "expert_high_steps": len(high_actions),
                }
            )
        except (OSError, json.JSONDecodeError, TypeError, AttributeError):
            continue
    ordered.sort(
        key=lambda row: (
            int(row["expert_steps"]),
            int(row["expert_high_steps"]),
            str(row["task_family"]),
            str(row["game_file"]),
        )
    )
    return ordered


def select_games_by_difficulty(
    data_dir: Path, split_name: str, count: int
) -> tuple[list[Path], list[dict[str, Any]]]:
    ordered = difficulty_order(data_dir, split_name)
    if len(ordered) < count:
        raise RuntimeError(f"requested {count} tasks but selected only {len(ordered)}")
    return [Path(row["game_file"]) for row in ordered[:count]], ordered


def structural_descriptor(family: str) -> tuple[ActionObservation, ...]:
    steps = [
        ActionObservation(
            "inspect environment",
            output_slots=("room_map",),
            check="reachable locations and visible objects are recorded",
        ),
        ActionObservation(
            "locate target object",
            input_slots=("room_map",),
            output_slots=("target_object",),
            precondition="the current receptacle has been inspected",
            check="the target object identity is observed",
        ),
        ActionObservation(
            "acquire target object",
            input_slots=("target_object",),
            output_slots=("held_object",),
            precondition="the target object is reachable",
            check="inventory contains the target object",
        ),
    ]
    if "clean_then" in family:
        steps.append(ActionObservation(
            "clean held object",
            input_slots=("held_object",),
            output_slots=("clean_object",),
            check="the environment confirms the object is clean",
        ))
    elif "heat_then" in family:
        steps.append(ActionObservation(
            "heat held object",
            input_slots=("held_object",),
            output_slots=("heated_object",),
            check="the environment confirms the object is hot",
        ))
    elif "cool_then" in family:
        steps.append(ActionObservation(
            "cool held object",
            input_slots=("held_object",),
            output_slots=("cooled_object",),
            check="the environment confirms the object is cool",
        ))
    if family == "look_at_obj_in_light":
        steps.extend([
            ActionObservation(
                "locate light source",
                input_slots=("room_map", "held_object"),
                output_slots=("light_source",),
                check="a usable lamp is observed",
            ),
            ActionObservation(
                "examine object under light",
                input_slots=("held_object", "light_source"),
                output_slots=("verified_goal",),
                check="the environment reports task completion",
            ),
        ])
    else:
        steps.extend([
            ActionObservation(
                "locate destination receptacle",
                input_slots=("room_map", "held_object"),
                output_slots=("destination",),
                check="the destination receptacle is observed",
            ),
            ActionObservation(
                "place required object",
                input_slots=("held_object", "destination"),
                output_slots=("verified_goal",),
                check="the environment reports task completion",
            ),
        ])
    return tuple(steps)


def extract_task(initial_observation: str) -> str:
    patterns = (
        r"Your task is to:\s*(.+?)(?:\n\n|$)",
        r"Task:\s*(.+?)(?:\n\n|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, initial_observation, flags=re.I | re.S)
        if match:
            return " ".join(match.group(1).split())
    return " ".join(initial_observation.split())[-1000:]


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")


def paired_no_memory_score(
    rows: Iterable[dict[str, Any]], game_file: Path, episode_index: int
) -> float | None:
    """Return the latest matched No Memory outcome for CoProMem feedback."""
    game_text = str(game_file)
    for row in reversed(list(rows)):
        if row.get("arm") != "no_memory":
            continue
        if (
            str(row.get("game_file", "")) == game_text
            or int(row.get("episode_index", -1)) == episode_index
        ):
            return float(bool(row.get("success")))
    return None


def latest_episode_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse append-only retries to the newest arm/task attempt for reporting."""
    latest: dict[tuple[str, str], tuple[int, dict[str, Any]]] = {}
    unkeyed: list[tuple[int, dict[str, Any]]] = []
    for index, row in enumerate(rows):
        arm = str(row.get("arm", ""))
        game_file = str(row.get("game_file", ""))
        if not arm or not game_file:
            unkeyed.append((index, row))
            continue
        latest[(arm, game_file)] = (index, row)
    keyed = list(latest.values())
    return [row for _, row in sorted([*keyed, *unkeyed], key=lambda item: item[0])]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def write_tracker(
    run_dir: Path,
    manifest: dict[str, Any],
    rows: Iterable[dict[str, Any]],
    status: str | None = None,
    current: dict[str, Any] | None = None,
) -> None:
    """Write a human-readable progress snapshot after each completed episode."""
    rows = latest_episode_rows(rows)
    arms = list(manifest.get("arms") or sorted({str(row.get("arm")) for row in rows}))
    task_count = int(manifest.get("task_count") or len(manifest.get("games") or []))
    expected = task_count * len(arms) if arms else task_count
    if status is None:
        status = "complete" if expected and len(rows) >= expected else "running"

    def clean(value: Any) -> str:
        return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")

    lines = [
        "# ALFWorld benchmark tracker",
        "",
        f"- Status: **{status}**",
        f"- Updated (UTC): `{datetime.now(timezone.utc).isoformat(timespec='seconds')}`",
        f"- Run ID: `{clean(manifest.get('run_id', run_dir.name))}`",
        f"- Split: `{clean(manifest.get('split'))}`",
        f"- Model: `{clean(manifest.get('model'))}`",
        f"- Max steps per task: `{clean(manifest.get('max_steps'))}`",
        f"- Sorted by difficulty: `{clean(manifest.get('difficulty_sort', False))}`",
        "",
        f"## Overall progress: {len(rows)}/{expected or '?'} episodes",
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
        lines.extend([
            "",
            "## Last completed episode",
            "",
            f"- Arm: `{clean(last.get('arm'))}`",
            f"- Task: `{clean(last.get('episode_index', 0) + 1)}/{task_count}`",
            f"- Family: `{clean(last.get('task_family'))}`",
            f"- Result: `{'success' if last.get('success') else 'failure'}`",
            f"- Steps: `{clean(last.get('steps'))}`",
            f"- Duration: `{clean(last.get('duration_seconds'))} s`",
        ])

    failures = [row for row in rows if not row.get("success")]
    if failures:
        lines.extend(["", "## Failed episodes", "", "| Arm | Task | Family | Steps |", "|---|---:|---|---:|"])
        for row in failures:
            lines.append(
                f"| `{clean(row.get('arm'))}` | {clean(row.get('episode_index', 0) + 1)} "
                f"| `{clean(row.get('task_family'))}` | {clean(row.get('steps'))} |"
            )

    if current:
        lines.extend([
            "",
            "## Current episode",
            "",
            f"- Arm: `{clean(current.get('arm'))}`",
            f"- Task: `{clean(current.get('episode_index', 0) + 1)}/{task_count}`",
            f"- Family: `{clean(current.get('task_family'))}`",
            f"- Step: `{clean(current.get('step'))}/{clean(current.get('max_steps'))}`",
            f"- Phase: `{clean(current.get('phase'))}`",
        ])
        if current.get("action"):
            lines.append(f"- Last action: `{clean(current.get('action'))}`")
        if current.get("task"):
            lines.append(f"- Task text: `{clean(current.get('task'))}`")
        if current.get("active_node_id"):
            lines.append(
                f"- CoProMem checkpoint: `{clean(current.get('active_node_id'))}` — "
                f"{clean(current.get('active_intent'))}"
            )
        if current.get("allowed_action_count") is not None:
            lines.append(
                f"- CoProMem action gate: `{clean(current.get('allowed_action_count'))}/"
                f"{clean(current.get('original_action_count'))}` actions allowed"
            )

    (run_dir / "tracker.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_episode(
    manager: Any,
    game_file: Path,
    arm: str,
    episode_index: int,
    agent: OpenRouterAgent,
    memory: COPROMEMMemoryModule | None,
    max_steps: int,
    seed: int,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    baseline_score: float | None = None,
    attempt_label: str | None = None,
) -> dict[str, Any]:
    family = task_family(game_file)
    descriptor = structural_descriptor(family)
    manager.game_files = [str(game_file)]
    manager.num_games = 1
    env = manager.init_env(batch_size=1)
    started = time.time()
    trajectory: list[dict[str, Any]] = []
    memory_guidance = ""
    retrieval: dict[str, Any] = {}
    retrieval_result = None
    controller: AlfworldCopromemController | None = None
    try:
        observations, infos = env.reset()
        observation = str(observations[0])
        task = extract_task(observation)
        if progress_callback is not None:
            progress_callback({
                "arm": arm,
                "episode_index": episode_index,
                "task_family": family,
                "task": task,
                "step": 1,
                "max_steps": max_steps,
                "phase": "waiting_for_model",
            })
        task_id = str(game_file.relative_to(Path(os.environ["ALFWORLD_DATA"])))
        if arm == "copromem_v2" and memory is not None:
            retrieval_result = memory.retrieve_memory(
                arm="copromem_v2",
                task_id=task_id,
                intent=task,
                domain=f"alfworld:{family}",
                structural_events=descriptor,
            )
            controller = AlfworldCopromemController(
                retrieval_result, task, task_id, descriptor
            )
            initial_admissible = [str(item) for item in infos["admissible_commands"][0]]
            controller.initialize(observation, initial_admissible)
            memory_guidance = retrieval_result.injected_text
            retrieval = {
                "compatibility": "conflict" if retrieval_result.should_veto else (
                    "compatible" if retrieval_result.selected_schema_id else "unknown"
                ),
                "schema_id": retrieval_result.selected_schema_id,
                "memory_id": retrieval_result.selected_memory_id,
                "procedure_ids": list(retrieval_result.injected_procedure_ids),
                "guidance": memory_guidance,
                "separated": retrieval_result.separated,
                "should_veto": retrieval_result.should_veto,
                "should_explore": retrieval_result.should_explore,
                "alternative_schema_id": (
                    retrieval_result.alternative_schema.schema_id
                    if retrieval_result.alternative_schema else None
                ),
                "contract_id": (
                    retrieval_result.contract.contract_id
                    if retrieval_result.contract else None
                ),
                "candidate_scores": dict(retrieval_result.candidate_scores),
                "controller_enabled": controller.enabled,
                "adapter_version": ADAPTER_VERSION,
            }

        won = False
        done = False
        for step in range(max_steps):
            admissible = [str(item) for item in infos["admissible_commands"][0]]
            control = None
            if controller is not None:
                control = controller.decide(observation, admissible)
                admissible = control.admissible
                memory_guidance = control.guidance
            if progress_callback is not None:
                progress_callback({
                    "arm": arm,
                    "episode_index": episode_index,
                    "task_family": family,
                    "task": task,
                    "step": step + 1,
                    "max_steps": max_steps,
                    "phase": "waiting_for_model",
                    "active_node_id": control.active_node_id if control else None,
                    "active_intent": control.active_intent if control else None,
                    "allowed_action_count": (
                        control.allowed_action_count if control else len(admissible)
                    ),
                    "original_action_count": (
                        control.original_action_count if control else len(admissible)
                    ),
                })
            action, provider = agent.choose_action(
                task,
                observation,
                admissible,
                [{"action": row["action"], "observation": row["observation"]}
                 for row in trajectory],
                memory_guidance,
                seed + episode_index * 1000 + step,
            )
            next_obs, _scores, dones, infos = env.step([action])
            observation = str(next_obs[0])
            done = bool(dones[0])
            won = bool((infos.get("won") or [False])[0])
            transition = None
            if controller is not None:
                next_admissible = [
                    str(item) for item in infos["admissible_commands"][0]
                ]
                transition = controller.observe(
                    action,
                    observation,
                    next_admissible,
                    done=done,
                    won=won,
                )
            trajectory.append({
                "step": step + 1,
                "action": action,
                "observation": observation,
                "done": done,
                "won": won,
                "provider": provider,
                "copromem_control": ({
                    "active_node_id": control.active_node_id,
                    "active_intent": control.active_intent,
                    "gated": control.gated,
                    "original_action_count": control.original_action_count,
                    "allowed_action_count": control.allowed_action_count,
                    "fallback": control.fallback,
                    "transition": transition,
                } if control is not None else None),
            })
            if progress_callback is not None:
                progress_callback({
                    "arm": arm,
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

        promotion = False
        learned_schema_id = None
        feedback_recorded = False
        if arm == "copromem_v2" and memory is not None:
            episode_id = f"alfworld:{episode_index}:{task_id}"
            if attempt_label:
                episode_id += f":{attempt_label}"
            observed_events = (
                controller.learning_events() if controller is not None else descriptor
            )
            learned_schema_id = memory.observe_events(
                episode_id, task_id, observed_events, won, f"alfworld:{family}"
            )
            promotion = memory.promote_episode(episode_id) if won else False
            if baseline_score is not None and retrieval_result is not None:
                memory.record_feedback(
                    retrieval_result.selected_schema_id,
                    task_id,
                    seed,
                    float(won),
                    float(baseline_score),
                )
                feedback_recorded = retrieval_result.selected_schema_id is not None
            if controller is not None:
                retrieval["controller"] = controller.summary()
        return {
            "arm": arm,
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
            "learned_schema_id": learned_schema_id,
            "promoted": promotion,
            "feedback_recorded": feedback_recorded,
            "attempt_label": attempt_label,
            "trajectory": trajectory,
        }
    finally:
        env.close()


def check_environment(config: dict[str, Any], games: list[Path]) -> dict[str, Any]:
    from alfworld.agents.environment import get_environment

    manager = get_environment("AlfredTWEnv")(
        config, train_eval=os.environ["ALFWORLD_SPLIT"]
    )
    manager.game_files = [str(games[0])]
    manager.num_games = 1
    env = manager.init_env(batch_size=1)
    try:
        observations, infos = env.reset()
        admissible = list(infos["admissible_commands"][0])
        fresh = COPROMEMMemoryModule(api_key="", seed_default_memories=False)
        descriptor = structural_descriptor(task_family(games[0]))
        retrieval = fresh.retrieve_memory(
            "copromem_v2", "smoke", extract_task(str(observations[0])),
            f"alfworld:{task_family(games[0])}", structural_events=descriptor,
        )
        schema_id = fresh.observe_events(
            "smoke:success", "smoke", descriptor, True,
            f"alfworld:{task_family(games[0])}",
        )
        promoted = fresh.promote_episode("smoke:success")
        learned = fresh.retrieve_memory(
            "copromem_v2", "smoke-transfer", extract_task(str(observations[0])),
            f"alfworld:{task_family(games[0])}", structural_events=descriptor,
        )
        return {
            "ok": True,
            "game": str(games[0]),
            "task_family": task_family(games[0]),
            "admissible_actions": len(admissible),
            "fresh_memory_guidance_is_empty": retrieval.injected_text == "",
            "promoted_schema_id": schema_id,
            "promotion_succeeded": promoted,
            "learned_memory_guidance_is_nonempty": bool(learned.injected_text),
            "provider_calls": 0,
        }
    finally:
        env.close()


def summarize(rows: Iterable[dict[str, Any]], stats: ProviderStats) -> dict[str, Any]:
    rows = latest_episode_rows(rows)
    arms: dict[str, dict[str, Any]] = {}
    for arm in sorted({row["arm"] for row in rows}):
        subset = [row for row in rows if row["arm"] == arm]
        wins = sum(bool(row["success"]) for row in subset)
        arms[arm] = {
            "tasks": len(subset),
            "successes": wins,
            "success_rate": wins / len(subset) if subset else 0.0,
            "average_steps": sum(row["steps"] for row in subset) / len(subset)
            if subset else 0.0,
            "retrieval_hits": sum(
                bool(row.get("retrieval", {}).get("guidance")) for row in subset
            ),
        }
    delta = None
    if "no_memory" in arms and "copromem_v2" in arms:
        delta = arms["copromem_v2"]["success_rate"] - arms["no_memory"]["success_rate"]
    return {
        "arms": arms,
        "copromem_minus_no_memory_success_rate": delta,
        "provider": asdict(stats),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="smoke-test without API calls")
    parser.add_argument("--tasks", type=int, default=None)
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--seed", type=int, default=1108)
    args = parser.parse_args()

    load_dotenv(ENV_FILE, override=False)
    data_dir = wsl_path(os.environ.get("ALFWORLD_DATA", str(DATA_ROOT)))
    split = os.environ.get("ALFWORLD_SPLIT", "eval_out_of_distribution")
    os.environ["ALFWORLD_SPLIT"] = split
    task_count = args.tasks or int(os.environ.get("ALFWORLD_TASKS", "6"))
    max_steps = args.max_steps or int(os.environ.get("ALFWORLD_MAX_STEPS", "30"))
    if task_count < 2 or max_steps < 1:
        raise ValueError("tasks must be >= 2 and max steps must be positive")

    random.seed(args.seed)
    np.random.seed(args.seed)
    config = load_config(data_dir, max_steps)
    games = select_games(data_dir, split, task_count)
    if args.check:
        print(json.dumps(check_environment(config, games), indent=2))
        return 0

    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise SystemExit(
            f"OPENROUTER_API_KEY is blank. Add it to {ENV_FILE} and rerun."
        )
    agent = OpenRouterAgent(
        api_key=api_key,
        model=os.environ.get("ALFWORLD_MODEL", "google/gemini-2.5-flash"),
        max_calls=int(os.environ.get("ALFWORLD_MAX_CALLS", "360")),
        max_usd=float(os.environ.get("ALFWORLD_MAX_USD", "1.00")),
        prompt_price_per_million=float(
            os.environ.get("ALFWORLD_MAX_PROMPT_PRICE_PER_M", "1.00")
        ),
        completion_price_per_million=float(
            os.environ.get("ALFWORLD_MAX_COMPLETION_PRICE_PER_M", "3.00")
        ),
    )

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RESULTS_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest = {
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "alfworld_commit": git_head(ALFWORLD_REPO),
        "copromem_commit": git_head(COPROMEM_REPO),
        "copromem_worktree_dirty": git_dirty(COPROMEM_REPO),
        "model": agent.model,
        "split": split,
        "seed": args.seed,
        "task_count": task_count,
        "max_steps": max_steps,
        "arms": ["no_memory", "copromem_v2"],
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

    from alfworld.agents.environment import get_environment

    all_rows: list[dict[str, Any]] = []
    events_path = run_dir / "episodes.jsonl"

    def track_step(current: dict[str, Any]) -> None:
        write_tracker(run_dir, manifest, all_rows, status="running", current=current)

    for arm in ("no_memory", "copromem_v2"):
        random.seed(args.seed)
        np.random.seed(args.seed)
        manager = get_environment("AlfredTWEnv")(config, train_eval=split)
        memory = (
            COPROMEMMemoryModule(api_key="", seed_default_memories=False)
            if arm == "copromem_v2" else None
        )
        for index, game in enumerate(games):
            baseline_score = (
                paired_no_memory_score(all_rows, game, index)
                if arm == "copromem_v2" else None
            )
            row = run_episode(
                manager, game, arm, index, agent, memory, max_steps, args.seed,
                progress_callback=track_step,
                baseline_score=baseline_score,
            )
            all_rows.append(row)
            append_jsonl(events_path, row)
            write_json(run_dir / "summary.json", summarize(all_rows, agent.stats))
            write_tracker(run_dir, manifest, all_rows)
            if memory is not None:
                write_json(run_dir / "copromem_state.json", memory.export_state())
            print(
                f"[{arm}] {index + 1}/{len(games)} "
                f"{row['task_family']} success={row['success']} steps={row['steps']} "
                f"spent_or_reserved=${agent.stats.charged_or_reserved_usd:.6f}",
                flush=True,
            )

    summary = summarize(all_rows, agent.stats)
    write_json(run_dir / "summary.json", summary)
    write_tracker(run_dir, manifest, all_rows, status="complete")
    print(json.dumps({"run_dir": str(run_dir), **summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
