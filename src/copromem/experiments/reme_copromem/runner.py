"""Shared execution boundary for the four-arm continuous CoProMem pilot.

This is deliberately independent of historical smoke runners.  It uses the
pinned upstream AppWorld agent for prompt construction, completion parsing and
memory HTTP lifecycle, while the worker remains the sole AppWorld executor and
official scorer.
"""
from __future__ import annotations

import contextlib
import inspect
import hashlib
import json
import os
import pathlib
import subprocess
import time
import urllib.request
from typing import Any, Callable, Iterator

from ...integrations.reme.transport import (
    AppendOnlyLedger, ContextCeilingTermination, LockedOpenAI, TruncationTermination,
)
from ...integrations.reme.upstream_executor import AppWorldProxy, CALL_ROLE, load_official_agent, safe_journal_path
from .strict_json import StrictJSONError, extract as extract_copromem_json
from ...benchmarks.appworld.adapter import AcquisitionIdentity, RawAcquisitionTrajectory
from ...benchmarks.appworld.adapter import CoProMemAppWorldAdapter, normalize_appworld_history
from ...online import ScoredCandidate, apply_task_batch
from .evidence_contract import bind as bind_execution_evidence
from .evidence_contract import bind_zero_action
from .evidence_contract import validate as validate_execution_evidence


ROOT = pathlib.Path(os.environ.get("COPROMEM_ROOT", pathlib.Path(__file__).resolve().parents[4]))
REME_PYTHON = os.environ.get("COPROMEM_REME_PYTHON", "/mnt/e/Project/AAMAS/reme-upstream-fixed-dynamic/bin/python")


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
                 progress: pathlib.Path, cap_usd: float, lifecycle_input_ceiling: int = 32768) -> None:
        self.port, self.name = port, name
        runtime = run / "services" / name
        self.log_path = run / "services" / f"{name}.log"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        # The upstream ReMe interpreter is intentionally a separate virtual
        # environment.  It still needs the maintained bridge package, whose
        # import root is ``ROOT/src`` rather than the repository root.
        env = {**os.environ, "PYTHONPATH": os.pathsep.join((str(ROOT / "src"), str(ROOT))), "PYTHONUNBUFFERED": "1",
               "OFFICIAL_REME_PORT": str(port),
               "OFFICIAL_REME_RUN_DIR": str(runtime), "OFFICIAL_REME_PROGRESS": str(progress),
               "OFFICIAL_REME_LEDGER": str(ledger), "OFFICIAL_PILOT_HARD_CAP": str(cap_usd),
               "OFFICIAL_REME_SERVICE_NAME": name,
               "OFFICIAL_PILOT_LIFECYCLE_INPUT_TOKEN_CEILING": str(lifecycle_input_ceiling)}
        self._log = self.log_path.open("a", encoding="utf-8", buffering=1)
        self.proc = subprocess.Popen([REME_PYTHON, "-u", "-m", "copromem.integrations.reme.corrected_service"],
                                     cwd=ROOT, env=env, stdout=self._log, stderr=subprocess.STDOUT)

    @property
    def base_url(self) -> str:
        # The pinned upstream AppWorld agent concatenates endpoint names rather
        # than using URL joining, while the local boundary strips trailing
        # slashes itself.  Preserve both contracts at this one boundary.
        return f"http://127.0.0.1:{self.port}/"

    def wait_healthy(self, timeout: float = 120.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"official ReMe service {self.name} exited ({self.proc.returncode})")
            try:
                with urllib.request.urlopen(self.base_url.rstrip("/") + "/health", timeout=2) as response:
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
             names: list[str], lifecycle_input_ceiling: int = 32768) -> Iterator[dict[str, ReMeService]]:
    instances = {name: ReMeService(port=18200 + index, name=name, run=run, ledger=ledger,
                                    progress=progress, cap_usd=cap_usd,
                                    lifecycle_input_ceiling=lifecycle_input_ceiling)
                 for index, name in enumerate(names)}
    try:
        # Probe all owned children concurrently. A child exit is detected on
        # its own probe rather than being hidden behind another service's full
        # timeout.
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(instances)) as pool:
            futures = [pool.submit(service.wait_healthy) for service in instances.values()]
            for future in futures: future.result()
        yield instances
    finally:
        for service in instances.values(): service.close()


def v5_budget_bound(*, call_limits: dict[str, int], historical_usd: float = 0.0,
                    lifecycle_input_ceiling: int = 131072) -> dict[str, float | int]:
    """Compute the complete registered v5 ceiling from frozen transport limits."""
    from ...integrations.reme.transport import (
        INPUT_PRICE, OUTPUT_PRICE, INPUT_TOKEN_CEILING, MAX_OUTPUT_TOKENS,
        LockedEmbeddings,
    )
    required = {"executor", "reme_lifecycle", "reme_embedding", "copromem_decomposition"}
    if set(call_limits) != required or any(int(value) < 0 for value in call_limits.values()):
        raise ValueError("v5 budget must register exactly the four provider-call roles")
    executor_per_call = INPUT_TOKEN_CEILING * INPUT_PRICE + MAX_OUTPUT_TOKENS * OUTPUT_PRICE
    lifecycle_per_call = lifecycle_input_ceiling * INPUT_PRICE + MAX_OUTPUT_TOKENS * OUTPUT_PRICE
    embedding_per_call = 10 * LockedEmbeddings.MAX_TOKENS_PER_ITEM * (0.02 / 1_000_000)
    decomposition_per_call = lifecycle_per_call
    contributions = {
        "executor_usd": int(call_limits["executor"]) * executor_per_call,
        "reme_lifecycle_usd": int(call_limits["reme_lifecycle"]) * lifecycle_per_call,
        "embedding_usd": int(call_limits["reme_embedding"]) * embedding_per_call,
        "copromem_decomposition_usd": int(call_limits["copromem_decomposition"]) * decomposition_per_call,
    }
    dispatchable = sum(contributions.values()) + float(historical_usd)
    contingency = dispatchable * 0.15
    return {**contributions, "executor_calls": int(call_limits["executor"]),
            "reme_lifecycle_calls": int(call_limits["reme_lifecycle"]),
            "embedding_calls": int(call_limits["reme_embedding"]),
            "copromem_decomposition_calls": int(call_limits["copromem_decomposition"]),
            "historical_charged_or_reserved_usd": float(historical_usd),
            "dispatchable_usd": dispatchable, "non_dispatchable_contingency_usd": contingency,
            "all_in_usd": dispatchable + contingency}


def configure_memory_transport(agent: Any,
                               memory_for_instruction: Callable[[str, str, dict[str, Any]], str] | None) -> None:
    """Disable only the upstream ReMe fallback for a CoProMem-backed arm."""
    if memory_for_instruction is not None:
        agent.get_memory = lambda _query: None


def invoke_post_score_update(callback: Callable[..., None], agent: Any, result: dict[str, Any], world: Any,
                             *, strict: bool, progress: pathlib.Path, trajectory_id: str, arm: str) -> None:
    """Invoke a durable post-score hook without changing legacy callback semantics."""
    try:
        if len(inspect.signature(callback).parameters) >= 3:
            callback(agent, result, world)
        else:
            callback(agent, result)
    except Exception as exc:
        append(progress, {"event": "post_score_update_failed", "trajectory_id": trajectory_id,
                          "arm": arm, "error_type": type(exc).__name__, "strict": strict})
        if strict:
            raise


def _observe_upstream_retrieval(response: Any) -> dict[str, Any]:
    """Return redacted ReMe retrieval provenance without altering its response.

    The official agent still owns request shape, retrieval ordering and prompt
    rendering.  This observer merely hashes the response returned by its
    existing ``get_memory`` method so aggregate reports cannot confuse an
    empty CoProMem callback with an empty upstream ReMe retrieval.
    """
    memory_list: list[Any] = []
    answer = ""
    if isinstance(response, dict):
        metadata = response.get("metadata")
        if isinstance(metadata, dict) and isinstance(metadata.get("memory_list"), list):
            memory_list = list(metadata["memory_list"])
        if isinstance(response.get("answer"), str):
            answer = str(response["answer"])
    stable_hashes = [digest(item) for item in memory_list]
    # This is the same text transformation the pinned upstream prompt method
    # uses; it is computed after the response has been returned, not supplied
    # back to the agent.
    rendered = __import__("re").sub(r"\bMemory\s*(\d+)\s*[:]", r"Experience \1:", answer) if memory_list else ""
    return {"retrieved_memory_count": len(memory_list), "retrieved_memory_sha256s": stable_hashes,
            "ordered_retrieval_sha256": digest(stable_hashes),
            "prompt_memory_sha256": digest(rendered), "retrieval_empty": not bool(memory_list),
            "retrieval_response_sha256": digest(response) if response is not None else digest(None)}


def _copromem_prompt_memory_text(guidance: str) -> str:
    """Render exactly one source-agent ``previous_memories`` item."""
    if not guidance:
        return ""
    return "Experience 1:\n When to use: Retrieved procedural guidance\n Content: " + guidance + "\n"


def model_visible_memory_binding(messages: list[dict[str, Any]], injected: str) -> dict[str, Any]:
    """Prove a callback's exact memory bytes entered the initial model prompt.

    A retrieval record alone is not evidence of prompt injection.  This helper
    is shared by the ReasoningBank port and existing memory arms: it examines
    the exact post-``prompt_messages`` payload that the locked executor sends,
    retains only a hash, and fails closed when non-empty callback text is not
    present byte-for-byte.
    """
    def contains(value: Any) -> bool:
        if isinstance(value, str):
            return injected in value
        if isinstance(value, dict):
            return any(contains(item) for item in value.values())
        if isinstance(value, list):
            return any(contains(item) for item in value)
        return False
    visible = not injected or contains(messages)
    if injected and not visible:
        raise RuntimeError("retrieved callback memory is absent from the model-visible prompt")
    return {"model_visible_prompt_sha256": digest(messages),
            "injected_memory_visible_in_initial_prompt": visible,
            "model_visible_memory_binding_sha256": digest({"prompt": digest(messages), "memory": digest(injected),
                                                             "visible": visible})}


def execute_trajectory(*, run: pathlib.Path, progress: pathlib.Path, ledger: AppendOnlyLedger,
                       api_key: str, all_task_ids: list[str], arm: str, task_id: str,
                       trial_id: int, seed: int, max_actions: int, temperature: float,
                       memory_base_url: str | None = None,
                       memory_for_instruction: Callable[[str, str, dict[str, Any]], str] | None = None,
                       phase: str = "evaluation", artifact_path: pathlib.Path | None = None,
                       post_score_update: Callable[[Any, dict[str, Any]], None] | None = None,
                       post_score_update_strict: bool = False,
                       execution_evidence: dict[str, Any] | None = None) -> dict[str, Any]:
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
                                    progress=progress, journal_path=journal, trajectory_id=key,
                                    execution_evidence=execution_evidence)
        # Shared acquisition is deliberately generated once without either
        # method's memory.  It is the common raw evidence source, not a sixth
        # memory arm.
        use_memory = arm not in {"no_memory", "shared_acquisition"}
        agent = Agent(index=seed, task_ids=[task_id], experiment_name="continuous_copromem_v5",
                      model_name="deepseek/deepseek-v4.1-flash", temperature=temperature,
                      max_interactions=max_actions, num_trials=1, use_memory=use_memory,
                      memory_base_url=(memory_base_url or "http://127.0.0.1:9/"),
                      use_memory_addition=False, use_memory_deletion=False)
        # CoProMem supplies its retrieval through ``memory_for_instruction``.
        # The upstream executor otherwise tries its own ReMe HTTP endpoint
        # whenever that callback legitimately yields empty guidance.  Empty
        # CoProMem guidance is a valid, provenance-recorded outcome, not a
        # reason to make an unregistered ReMe retrieval request.
        configure_memory_transport(agent, memory_for_instruction)
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
            upstream_retrieval: dict[str, Any] | None = None
            if memory_for_instruction is not None:
                tool_meta = {"app_descriptions": world.task.app_descriptions, "supervisor": world.task.supervisor}
                injected = memory_for_instruction(world.task.instruction, "appworld", tool_meta)
                if injected:
                    previous = [{"when_to_use": "Retrieved procedural guidance", "content": injected}]
            elif arm.startswith("official_upstream_reme"):
                # Passive only: the wrapper delegates the unchanged response
                # object to the upstream agent.  It never adds, removes or
                # rewrites a memory or prompt token.
                original_get_memory = agent.get_memory
                def observed_get_memory(query: str) -> Any:
                    nonlocal upstream_retrieval
                    response = original_get_memory(query)
                    upstream_retrieval = _observe_upstream_retrieval(response)
                    return response
                agent.get_memory = observed_get_memory
            agent.prompt_messages(0, 0, previous, world)
            initial_prompt_messages_sha256 = digest(agent.history[0][0])
            memory_visibility = model_visible_memory_binding(agent.history[0][0], injected)
            termination = "completed"
            last_tokens: int | None = None
            terminal_executor: dict[str, Any] | None = None
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
                    termination = "truncation_termination"
                    record = getattr(agent.llm_client.chat.completions, "last_record", None)
                    terminal_executor = dict(record) if isinstance(record, dict) else None
                    break
                code, _ = agent.extract_code_and_fix_content(completion)
                agent.history[0][0].append({"role": "assistant", "content": code})
                output = world.execute(code)
                agent.history[0][0].append({"role": "user", "content": "Output:\n```\n" + output + "```\n\n"})
                if world.task_completed(): break
            # The upstream agent's initial score remains auditable as
            # ``pre_trajectory``.  Mark exactly one later scorer call as the
            # terminal binding before invoking the unchanged upstream method.
            world.mark_post_trajectory_score()
            after = agent.get_reward(world)  # AppWorldProxy durably journals official score.
            result = {"trajectory_id": key, "arm": arm, "task_id": task_id, "trial_id": trial_id,
                      "seed": seed, "before_score": before, "after_score": after,
                      "actions": sum(m["role"] == "assistant" for m in agent.history[0][0]),
                      "termination": termination, "history": agent.history[0][0],
                      "history_sha256": digest(agent.history[0][0]), "injected_memory_sha256": digest(injected),
                      "injected_memory_nonempty": bool(injected),
                      "initial_prompt_messages_sha256": initial_prompt_messages_sha256,
                      **memory_visibility,
                      "execution_evidence_path": str(journal.with_suffix(".execution-evidence.jsonl")) if execution_evidence else None}
            if memory_for_instruction is not None:
                result.update({"copromem_callback_guidance_sha256": digest(injected),
                               "copromem_callback_guidance_nonempty": bool(injected),
                               "prompt_memory_injection_sha256": digest(_copromem_prompt_memory_text(injected))})
            if arm.startswith("official_upstream_reme"):
                result["reme_retrieval_provenance"] = upstream_retrieval or {
                    "retrieved_memory_count": 0, "retrieved_memory_sha256s": [],
                    "ordered_retrieval_sha256": digest([]), "prompt_memory_sha256": digest(""),
                    "retrieval_empty": True, "retrieval_response_sha256": digest(None)}
            if execution_evidence is not None:
                evidence_path = pathlib.Path(str(result["execution_evidence_path"]))
                if result["actions"] == 0 and terminal_executor is not None:
                    manifest_path = run / "manifest.json"
                    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    source_commit = str(os.environ.get("COPROMEM_SOURCE_COMMIT") or
                                        manifest.get("git_commit") or "")
                    runtime_identity = run / "runtime-identity.json"
                    if not runtime_identity.is_file():
                        raise RuntimeError("zero-action evidence requires durable runtime identity")
                    result.update(bind_zero_action(
                        journal=evidence_path, scorer_journal=journal, run_root=run,
                        registry_sha256=execution_evidence["registry_sha256"], trajectory_id=key,
                        after_score=float(after), termination=termination,
                        executor_record=terminal_executor, manifest_sha256=manifest_sha,
                        source_commit=source_commit, task_id=task_id, arm=arm, trial_id=trial_id,
                        seed=seed, history_sha256=result["history_sha256"],
                        runtime_identity_sha256=hashlib.sha256(runtime_identity.read_bytes()).hexdigest(),
                    ))
                else:
                    result.update(bind_execution_evidence(journal=evidence_path, run_root=run,
                                                          registry_sha256=execution_evidence["registry_sha256"],
                                                          scorer_journal=journal, trajectory_id=key, task_id=task_id,
                                                          after_score=float(after), history_sha256=result["history_sha256"]))
                validate_execution_evidence(result, run_root=run,
                                            expected_registry_sha256=execution_evidence["registry_sha256"])
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
                # The durable scorer artifact above is deliberately written
                # before an upstream Dynamic-memory update.  Strict Dynamic
                # callers propagate a checkpoint failure; legacy users keep
                # the historical best-effort callback contract.
                invoke_post_score_update(post_score_update, agent, result, world,
                                         strict=post_score_update_strict, progress=progress,
                                         trajectory_id=key, arm=arm)
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
                     minimum_successful_families: int = 6,
                     fail_closed: bool = True) -> dict[str, Any]:
    successes = [row for row in records if float(row.get("after_score", 0)) == 1.0]
    families = {str(row["task_id"])[:7] for row in successes}
    result = {"planned": len(records), "full_successes": len(successes),
              "successful_families": len(families), "input_sha256": digest([
                  {"identity": row["acquisition_identity"], "artifact": row["source_artifact_sha256"]}
                  for row in records])}
    result["passed"] = (len(records) == expected_records and len(successes) >= minimum_full_successes
                        and len(families) >= minimum_successful_families)
    if fail_closed and not result["passed"]:
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
                                  "source_artifact_sha256": row["source_artifact_sha256"],
                                  "official_score": float(row["after_score"])},
                      events=normalize_appworld_history(row["history"], float(row["after_score"]) == 1.0)))
    return output


def decomposition_json_call(*, run: pathlib.Path, progress: pathlib.Path,
                            ledger: AppendOnlyLedger, api_key: str,
                            role_prefix: str = "copromem_decomposition:acquisition") -> Callable[..., dict[str, Any] | None]:
    """Use the same ledgered, cached decomposition boundary in acquisition and evaluation."""
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
                    accepted = row["accepted_object"]
                    if (row.get("schema_name") != schema_name
                            or row.get("accepted_object_sha256") != hashlib.sha256(accepted.encode()).hexdigest()):
                        raise RuntimeError("decomposition cache integrity mismatch")
                    parsed, _, _ = extract_copromem_json(schema_name or "", row["accepted_object"], "stop", False)
                    if parsed != row.get("parsed"):
                        raise RuntimeError("decomposition cache parsed object mismatch")
                    append(provenance, {"event": "decomposition_cache_reused", "request_sha256": request_hash})
                    return parsed
        client = LockedOpenAI(api_key=api_key, ledger=ledger, progress=progress,
                              role=f"{role_prefix}:{schema_name or 'unknown'}")
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
               "accepted_object_sha256": hashlib.sha256(accepted.encode()).hexdigest(),
               "object_span": list(span), "parsed": parsed}
        append(cache, row)
        append(provenance, {"event": "decomposition_accepted", "request_sha256": request_hash,
                            "accepted_object_sha256": hashlib.sha256(accepted.encode()).hexdigest()})
        return parsed

    return json_call


def construct_copromem(*, run: pathlib.Path, progress: pathlib.Path, ledger: AppendOnlyLedger,
                       api_key: str, raw: list[RawAcquisitionTrajectory], call_cap: int = 320) -> tuple[dict[str, Any], str]:
    """Build a mutable warm start from public, scored train trajectories."""
    adapter = CoProMemAppWorldAdapter(api_key="")
    by_task: dict[str, list[RawAcquisitionTrajectory]] = {}
    for episode in raw:
        by_task.setdefault(episode.identity.task_id, []).append(episode)
    for episodes in by_task.values():
        apply_task_batch(adapter, [ScoredCandidate(
            trajectory=episode, score=float(episode.task_state.get("official_score", episode.success)),
            cost_usd=0.0, actions=len(episode.actions)) for episode in episodes])
    state = adapter.export_state()
    state_hash = digest(state)
    write_json(run / "copromem" / "initial-state.json", state)
    append(progress, {"event": "copromem_train_warm_start", "state_sha256": state_hash,
                      "episode_count": len(raw)})
    return state, state_hash
