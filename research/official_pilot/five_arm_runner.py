"""Shared five-arm execution boundary for the corrected fixed/dynamic pilot.

This is deliberately independent of historical smoke runners.  It uses the
pinned upstream AppWorld agent for prompt construction, completion parsing and
memory HTTP lifecycle, while the worker remains the sole AppWorld executor and
official scorer.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import pathlib
import subprocess
import time
import urllib.request
from typing import Any, Callable, Iterator

from research.official_pilot.locked_openrouter import (
    AppendOnlyLedger, ContextCeilingTermination, LockedOpenAI, TruncationTermination,
)
from research.official_pilot.upstream_executor import AppWorldProxy, CALL_ROLE, load_official_agent, safe_journal_path
from research.official_pilot.strict_copromem_json import StrictJSONError, extract as extract_copromem_json
from src.copromem.appworld_comparison_adapter import AcquisitionIdentity, RawAcquisitionTrajectory
from src.copromem.appworld_comparison_adapter import CoProMemAppWorldAdapter


ROOT = pathlib.Path("/mnt/e/Project/AAMAS/COPROMEM")
REME_PYTHON = "/mnt/e/Project/AAMAS/reme-upstream-fixed-dynamic/bin/python"


def append(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush(); os.fsync(handle.fileno())


def write_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, path)


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def official_post(base_url: str, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(base_url.rstrip("/") + "/" + endpoint,
        data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


class ReMeService:
    """One isolated official source service and its own durable log."""
    def __init__(self, *, port: int, name: str, run: pathlib.Path, ledger: pathlib.Path,
                 progress: pathlib.Path, cap_usd: float) -> None:
        self.port, self.name = port, name
        runtime = run / "services" / name
        self.log_path = run / "services" / f"{name}.log"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, "PYTHONPATH": str(ROOT), "OFFICIAL_REME_PORT": str(port),
               "OFFICIAL_REME_RUN_DIR": str(runtime), "OFFICIAL_REME_PROGRESS": str(progress),
               "OFFICIAL_REME_LEDGER": str(ledger), "OFFICIAL_PILOT_HARD_CAP": str(cap_usd)}
        self._log = self.log_path.open("a", encoding="utf-8")
        self.proc = subprocess.Popen([REME_PYTHON, "-m", "research.official_pilot.corrected_reme_service"],
                                     cwd=ROOT, env=env, stdout=self._log, stderr=subprocess.STDOUT)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def wait_healthy(self, timeout: float = 120.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"official ReMe service {self.name} exited ({self.proc.returncode})")
            try:
                with urllib.request.urlopen(self.base_url + "/health", timeout=2) as response:
                    if response.status == 200:
                        return
            except OSError:
                time.sleep(1)
        raise RuntimeError(f"official ReMe service {self.name} health timeout")

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try: self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired: self.proc.kill(); self.proc.wait(timeout=10)
        self._log.close()


@contextlib.contextmanager
def services(run: pathlib.Path, ledger: pathlib.Path, progress: pathlib.Path, cap_usd: float,
             names: list[str]) -> Iterator[dict[str, ReMeService]]:
    instances = {name: ReMeService(port=18200 + index, name=name, run=run, ledger=ledger,
                                    progress=progress, cap_usd=cap_usd)
                 for index, name in enumerate(names)}
    try:
        for service in instances.values(): service.wait_healthy()
        yield instances
    finally:
        for service in instances.values(): service.close()


def execute_trajectory(*, run: pathlib.Path, progress: pathlib.Path, ledger: AppendOnlyLedger,
                       api_key: str, all_task_ids: list[str], arm: str, task_id: str,
                       trial_id: int, seed: int, max_actions: int, temperature: float,
                       memory_base_url: str | None = None,
                       memory_for_instruction: Callable[[str, str, dict[str, Any]], str] | None = None,
                       phase: str = "evaluation", artifact_path: pathlib.Path | None = None,
                       post_score_update: Callable[[Any, dict[str, Any]], None] | None = None) -> dict[str, Any]:
    """Run one arm/task/trial without changing the source agent's decisions.

    ``memory_for_instruction`` is invoked exactly once after the worker exposes
    the public instruction. It is used only by CoProMem; ReMe uses the source
    retrieval call unchanged.  The returned text is formatted through the
    source agent's existing ``previous_memories`` branch.
    """
    if phase not in {"acquisition", "evaluation"}:
        raise ValueError("unregistered trajectory phase")
    key = f"{phase}:{arm}:{task_id}:trial={trial_id}:seed={seed}"
    journal = safe_journal_path(run / "journals", key)
    token = CALL_ROLE.set(f"executor:{arm}:{task_id}:trial={trial_id}:seed={seed}")
    try:
        Agent = load_official_agent(allowed_tasks=all_task_ids, api_key=api_key, ledger=ledger,
                                    progress=progress, journal_path=journal, trajectory_id=key)
        # Shared acquisition is deliberately generated once without either
        # method's memory.  It is the common raw evidence source, not a sixth
        # memory arm.
        use_memory = arm not in {"no_memory", "shared_acquisition"}
        agent = Agent(index=seed, task_ids=[task_id], experiment_name="corrected_fixed_dynamic_v1",
                      model_name="deepseek/deepseek-v4.1-flash", temperature=temperature,
                      max_interactions=max_actions, num_trials=1, use_memory=use_memory,
                      memory_base_url=(memory_base_url or "http://127.0.0.1:9/"),
                      use_memory_addition=False, use_memory_deletion=False)
        # Fixed must remain read-only even though the source agent normally
        # records retrieval metadata. Dynamic post-score updates are handled
        # separately, only after this durable result record exists.
        if arm.endswith("_fixed"):
            agent.update_memory_information = lambda *_a, **_k: None
            agent.delete_memory = lambda *_a, **_k: None
        with AppWorldProxy(task_id=task_id, experiment_name=key) as world:
            before = agent.get_reward(world)
            injected = ""
            previous: list[dict[str, str]] = []
            if memory_for_instruction is not None:
                tool_meta = {"app_descriptions": world.task.app_descriptions, "supervisor": world.task.supervisor}
                injected = memory_for_instruction(world.task.instruction, "appworld", tool_meta)
                if injected:
                    previous = [{"when_to_use": "Retrieved procedural guidance", "content": injected}]
            agent.prompt_messages(0, 0, previous, world)
            termination = "completed"
            last_tokens: int | None = None
            for _ in range(max_actions):
                try:
                    completion = agent.call_llm(agent.history[0][0])
                    last_tokens = getattr(agent.llm_client.chat.completions, "last_accepted_prompt_tokens", last_tokens)
                except ContextCeilingTermination as exc:
                    termination = "context_ceiling_termination"
                    append(progress, {"event": termination, "trajectory_id": key, "completed_actions":
                                     sum(m["role"] == "assistant" for m in agent.history[0][0]),
                                     "last_accepted_prompt_tokens": last_tokens, "ceiling": exc.ceiling})
                    break
                except TruncationTermination:
                    termination = "truncation_termination"; break
                code, _ = agent.extract_code_and_fix_content(completion)
                agent.history[0][0].append({"role": "assistant", "content": code})
                output = world.execute(code)
                agent.history[0][0].append({"role": "user", "content": "Output:\n```\n" + output + "```\n\n"})
                if world.task_completed(): break
            after = agent.get_reward(world)  # AppWorldProxy durably journals official score.
            result = {"trajectory_id": key, "arm": arm, "task_id": task_id, "trial_id": trial_id,
                      "seed": seed, "before_score": before, "after_score": after,
                      "actions": sum(m["role"] == "assistant" for m in agent.history[0][0]),
                      "termination": termination, "history": agent.history[0][0],
                      "history_sha256": digest(agent.history[0][0]), "injected_memory_sha256": digest(injected),
                      "injected_memory_nonempty": bool(injected)}
            if artifact_path is not None:
                write_json(artifact_path, result)
            append(progress, {"event": "trajectory_scored", "phase": phase, "trajectory_id": key, "arm": arm,
                              "task_id": task_id, "trial_id": trial_id, "score": after,
                              "actions": result["actions"], "termination": termination,
                              "history_sha256": result["history_sha256"]})
            # This callback is intentionally after both official scoring and
            # artifact durability. Its failures never remove or replay the
            # already-scored trajectory.
            if post_score_update is not None:
                try:
                    post_score_update(agent, result)
                except Exception as exc:
                    append(progress, {"event": "post_score_update_failed", "trajectory_id": key,
                                      "arm": arm, "error_type": type(exc).__name__})
            return result
    finally:
        CALL_ROLE.reset(token)


def acquisition_pool(*, run: pathlib.Path, progress: pathlib.Path, ledger: AppendOnlyLedger,
                     api_key: str, acquisition_ids: list[str], evaluation_ids: list[str], seeds: list[int],
                     max_actions: int, temperature: float) -> list[dict[str, Any]]:
    """Generate each registered shared raw trajectory at most once."""
    records: list[dict[str, Any]] = []
    for task_id in acquisition_ids:
        for trajectory_index, seed in enumerate(seeds):
            artifact = run / "acquisition" / f"{task_id}--seed_{seed}--trajectory_{trajectory_index}.json"
            if artifact.exists():
                row = json.loads(artifact.read_text(encoding="utf-8"))
            else:
                row = execute_trajectory(run=run, progress=progress, ledger=ledger, api_key=api_key,
                    all_task_ids=acquisition_ids + evaluation_ids, arm="shared_acquisition", task_id=task_id,
                    trial_id=trajectory_index, seed=seed, max_actions=max_actions, temperature=temperature,
                    phase="acquisition", artifact_path=artifact)
            instruction = ""
            for message in row.get("history", []):
                if message.get("role") == "user":
                    instruction = str(message.get("content") or "")
                    break
            if not instruction:
                raise RuntimeError(f"acquisition artifact lacks public task instruction: {artifact}")
            row["source_artifact"] = str(artifact)
            row["source_artifact_sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
            row["instruction"] = instruction
            row["acquisition_identity"] = AcquisitionIdentity(task_id, seed, trajectory_index).value
            records.append(row)
    return records


def acquisition_gate(records: list[dict[str, Any]], *, expected_records: int = 24,
                     minimum_full_successes: int = 8,
                     minimum_successful_families: int = 6) -> dict[str, Any]:
    successes = [row for row in records if float(row.get("after_score", 0)) == 1.0]
    families = {str(row["task_id"])[:7] for row in successes}
    result = {"planned": len(records), "full_successes": len(successes),
              "successful_families": len(families), "input_sha256": digest([
                  {"identity": row["acquisition_identity"], "artifact": row["source_artifact_sha256"]}
                  for row in records])}
    if (len(records) != expected_records or len(successes) < minimum_full_successes
            or len(families) < minimum_successful_families):
        raise RuntimeError("preregistered acquisition gate failed")
    return result


def raw_acquisition_trajectories(records: list[dict[str, Any]]) -> list[RawAcquisitionTrajectory]:
    """Convert frozen shared agent histories to CoProMem's native input type."""
    output: list[RawAcquisitionTrajectory] = []
    for row in records:
        actions = tuple(str(message.get("content") or "") for message in row["history"]
                        if message.get("role") == "assistant")
        task_id, seed_text, trajectory_text = str(row["acquisition_identity"]).split("::")
        identity = AcquisitionIdentity(task_id, int(seed_text.split("=")[1]),
                                       int(trajectory_text.split("=")[1]))
        output.append(RawAcquisitionTrajectory(identity=identity, intent=row["instruction"], domain="appworld",
                      success=float(row["after_score"]) == 1.0, actions=actions,
                      task_state={"history_sha256": row["history_sha256"],
                                  "source_artifact_sha256": row["source_artifact_sha256"]}))
    return output


def construct_copromem(*, run: pathlib.Path, progress: pathlib.Path, ledger: AppendOnlyLedger,
                       api_key: str, raw: list[RawAcquisitionTrajectory], call_cap: int = 320) -> tuple[dict[str, Any], str]:
    """Build the single acquired CoProMem state through strict JSON calls."""
    cache = run / "copromem" / "decomposition-cache.jsonl"
    provenance = run / "copromem" / "decomposition-provenance.jsonl"

    def json_call(*, system_prompt: str, user_prompt: str, max_tokens: int,
                  schema_name: str | None = None, **_: Any) -> dict[str, Any] | None:
        request_hash = digest({"system": system_prompt, "user": user_prompt, "schema": schema_name,
                               "max_tokens": min(max_tokens, 2048)})
        if cache.exists():
            for line in cache.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                if row.get("request_sha256") == request_hash:
                    parsed, _, _ = extract_copromem_json(schema_name or "", row["accepted_object"], "stop", False)
                    append(provenance, {"event": "decomposition_cache_reused", "request_sha256": request_hash})
                    return parsed
        client = LockedOpenAI(api_key=api_key, ledger=ledger, progress=progress,
                              role=f"copromem_decomposition:{schema_name or 'unknown'}")
        response = client.chat.completions.create(model="deepseek/deepseek-v4.1-flash", stream=False,
            max_tokens=min(max_tokens, 2048), temperature=0.0,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}])
        choice = response.choices[0]
        content = str(choice.message.content or "")
        try:
            parsed, accepted, span = extract_copromem_json(schema_name or "", content, choice.finish_reason,
                                                            bool(choice.message.tool_calls))
        except StrictJSONError as exc:
            append(provenance, {"event": "decomposition_rejected", "request_sha256": request_hash,
                                "finish_reason": choice.finish_reason, "content_sha256": hashlib.sha256(content.encode()).hexdigest()})
            raise RuntimeError("CoProMem response violates frozen JSON contract") from exc
        row = {"request_sha256": request_hash, "schema_name": schema_name, "finish_reason": choice.finish_reason,
               "content_sha256": hashlib.sha256(content.encode()).hexdigest(), "accepted_object": accepted,
               "object_span": list(span), "parsed": parsed}
        append(cache, row)
        append(provenance, {"event": "decomposition_accepted", "request_sha256": request_hash,
                            "accepted_object_sha256": hashlib.sha256(accepted.encode()).hexdigest()})
        return parsed

    adapter = CoProMemAppWorldAdapter(api_key="locked", model="deepseek/deepseek-v4.1-flash",
        provider_only="deepseek", reasoning_effort="none", llm_json_call=json_call,
        decomposition_call_cap=call_cap)
    for episode in raw:
        adapter.ingest(episode)
    adapter.consolidate()
    state = adapter.export_state()
    state_hash = digest(state)
    write_json(run / "copromem" / "initial-state.json", state)
    append(progress, {"event": "copromem_initial_bank_frozen", "state_sha256": state_hash,
                      "episode_count": len(raw)})
    return state, state_hash
