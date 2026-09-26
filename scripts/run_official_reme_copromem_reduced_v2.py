#!/usr/bin/env python3
"""Standalone, checkpointed official-ReMe / CoProMem reduced-v2 pilot.

This runner is intentionally serial: two-way concurrency is disabled until an
independent AppWorld/scorer isolation proof is retained for this exact runner.
It can be launched once and resumed safely; records are written before each
network dispatch (inside the locked transports) and before each native action.
"""
from __future__ import annotations

import argparse, hashlib, json, os, pathlib, subprocess, sys, time, urllib.request
from contextlib import contextmanager
from typing import Any

ROOT = pathlib.Path("/mnt/e/Project/AAMAS/COPROMEM")
sys.path.insert(0, str(ROOT))
from research.official_pilot.locked_openrouter import (AppendOnlyLedger, ContextCeilingTermination,
    DispatchFailure, LockedOpenAI)
from research.official_pilot.upstream_executor import AppWorldProxy, CALL_ROLE, load_official_agent, safe_journal_path
from research.official_pilot.strict_copromem_json import StrictJSONError, classify, extract as extract_copromem_json
from research.official_pilot.evaluation_lifecycle import dynamic_post_trial_update
from src.copromem.appworld_comparison_adapter import (AcquisitionIdentity, CoProMemAppWorldAdapter,
    RawAcquisitionTrajectory, TrialInput)

RUN = ROOT / "artifacts/research/official_reme_copromem_pilot/reduced_v2"
MANIFEST = RUN / "manifest.json"
PROGRESS = ROOT / "artifacts/research/official_reme_copromem_pilot/progress.jsonl"
LEDGER = RUN / "successor-ledger.jsonl"
STATUS = RUN / "runner-status.json"
SERVICE_PY = "/mnt/e/Project/AAMAS/reme-official-service-v3/bin/python"
HARD_CAP = float(os.environ.get("OFFICIAL_PILOT_HARD_CAP", "35"))
REPORT_SCRIPT = pathlib.Path(os.environ.get("OFFICIAL_PILOT_REPORT_SCRIPT",
    str(ROOT / "research/scripts/build_reduced_v2_final_report.py")))


def env_values() -> dict[str, str]:
    data: dict[str, str] = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1); data[key.strip()] = value.strip().strip("'\"")
    return data


def write_json(path: pathlib.Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def append(path: pathlib.Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n"); f.flush(); os.fsync(f.fileno())


def sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def disk_guard() -> None:
    available = os.statvfs("/mnt/c").f_bavail * os.statvfs("/mnt/c").f_frsize
    floor_gb = float(os.environ.get("OFFICIAL_PILOT_C_FLOOR_GB", "10"))
    if available < floor_gb * 1024 ** 3:
        raise RuntimeError("Windows C storage floor would be breached")


def completed(key: str) -> bool:
    path = RUN / "completed.jsonl"
    if not path.exists(): return False
    return any(json.loads(line).get("key") == key for line in path.read_text(encoding="utf-8").splitlines() if line)


def mark_completed(key: str, payload: dict[str, Any]) -> None:
    append(RUN / "completed.jsonl", {"key": key, "time_ns": time.time_ns(), **payload})


class ReMeService:
    def __init__(self, port: int, name: str, attempt: str) -> None:
        self.port, self.name, self.attempt = port, name, attempt
        self.log = RUN / "services" / f"{attempt}-{name}.log"; self.log.parent.mkdir(parents=True, exist_ok=True)
        proc_env = {**os.environ, "PYTHONPATH": str(ROOT), "OFFICIAL_REME_PORT": str(port),
                    "OFFICIAL_REME_RUN_DIR": str(RUN / "services" / attempt / name),
                    "OFFICIAL_REME_PROGRESS": str(PROGRESS), "OFFICIAL_REME_LEDGER": str(LEDGER)}
        self._out = self.log.open("a", encoding="utf-8")
        self.proc = subprocess.Popen([SERVICE_PY, "-m", "research.official_pilot.reme_service"], cwd=ROOT,
                                     env=proc_env, stdout=self._out, stderr=subprocess.STDOUT)

    def health(self) -> bool:
        if self.proc.poll() is not None:
            raise RuntimeError(f"official ReMe service {self.name} exited with code {self.proc.returncode}")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=1) as response:
                return response.status == 200
        except Exception:
            return False

    def close(self) -> None:
        if self.proc.poll() is None: self.proc.terminate()
        try: self.proc.wait(20)
        except subprocess.TimeoutExpired: self.proc.kill()
        self._out.close()


@contextmanager
def reme_services(attempt: str):
    # Start both independently before polling so startup is concurrent and
    # each service has its own process/log/artifact directory.
    fixed, dynamic = ReMeService(18102, "fixed", attempt), ReMeService(18103, "dynamic", attempt)
    try:
        deadline = time.monotonic() + 120
        ready: set[str] = set()
        while time.monotonic() < deadline:
            for service in (fixed, dynamic):
                if service.name not in ready and service.health(): ready.add(service.name)
            if len(ready) == 2: break
            time.sleep(1)
        if len(ready) != 2: raise RuntimeError("official ReMe service health timeout")
        append(PROGRESS,{"event":"reme_services_healthy","attempt":attempt,"ports":[18102,18103]})
        yield "http://127.0.0.1:18102/", "http://127.0.0.1:18103/"
    finally:
        fixed.close(); dynamic.close()


def post(base: str, endpoint: str, data: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(base + endpoint, data=json.dumps(data).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as response:
        return json.loads(response.read().decode())


def run_upstream(task_id: str, seed: int, arm: str, base: str | None, api_key: str,
                 ledger: AppendOnlyLedger, all_ids: list[str], journal: pathlib.Path) -> dict[str, Any]:
    trajectory_id = f"acquisition:{task_id}:seed={seed}"
    journal = safe_journal_path(journal.parent, trajectory_id)
    journal.parent.mkdir(parents=True, exist_ok=True)
    AppWorldProxy.journal_path = journal
    token = CALL_ROLE.set(f"executor:{arm}:{task_id}:seed={seed}")
    try:
        Agent = load_official_agent(allowed_tasks=all_ids, api_key=api_key, ledger=ledger,
                                    progress=PROGRESS, journal_path=journal, trajectory_id=trajectory_id)
        kwargs: dict[str, Any] = {"index": seed, "task_ids": [task_id], "experiment_name": f"reduced_v2_{arm}",
            "model_name": "deepseek/deepseek-v4.1-flash", "max_interactions": 30, "num_trials": 1,
            "use_memory": arm != "no_memory", "memory_base_url": base or "http://127.0.0.1:9/",
            "use_memory_addition": arm == "official_upstream_reme_dynamic",
            "use_memory_deletion": arm == "official_upstream_reme_dynamic"}
        agent = Agent(**kwargs)
        outcome = agent.execute()[0]
        # task history is retained privately for upstream lifecycle input; public
        # progress only records a hash and official score.
        return outcome
    finally:
        CALL_ROLE.reset(token)


def acquisition(manifest: dict[str, Any], api_key: str, ledger: AppendOnlyLedger) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    ids = manifest["acquisition"]["task_ids"]
    for task_id, seed in zip(ids, manifest["acquisition"]["seeds"]):
        key = f"acquisition:{task_id}:{seed}"
        artifact = RUN / "acquisition" / f"{task_id}-{seed}.json"
        if completed(key):
            if artifact.exists():
                records.append(json.loads(artifact.read_text(encoding="utf-8")))
            else:
                # A power-loss record with settled calls but no replayable
                # action transcript is terminal by protocol: never regenerate
                # it. It is retained in the acquisition population as an
                # explicitly unavailable/incomplete episode, not fabricated.
                append(PROGRESS,{"event":"trajectory_skipped_no_replay","stage":"acquisition",
                                 "task_id":task_id,"seed":seed,"reason":"durable_interrupted_record"})
            continue
        disk_guard()
        outcome = run_upstream(task_id, seed, "no_memory", None, api_key, ledger, ids + manifest["evaluation"]["task_ids"],
                               RUN / "journals" / f"{key}.jsonl")
        write_json(artifact, outcome)
        mark_completed(key, {"artifact": str(artifact.relative_to(ROOT)), "sha256": sha(outcome)})
        append(PROGRESS, {"event":"trajectory_complete", "stage":"acquisition", "task_id":task_id,
                          "score":outcome["after_score"], "history_sha256":sha(outcome["task_history"])})
        records.append(outcome)
    return records


def construct_reme(base: str, raw: list[dict[str, Any]], name: str, attempt: str) -> None:
    # Pinned default.yaml registers summary_task_memory as ... >>
    # UpdateVectorStoreOp(). It persists itself; no invented add endpoint is
    # permitted. Persist each response before issuing the next official call.
    checkpoint = RUN / "lifecycle" / attempt / f"{name}.jsonl"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    for item in raw:
        if checkpoint.exists() and any(json.loads(line).get("task_id") == item["task_id"]
                                     for line in checkpoint.read_text(encoding="utf-8").splitlines() if line):
            continue
        response = post(base, "summary_task_memory", {"trajectories": [{"task_id": item["task_id"],
                       "messages": item["task_history"], "score": item["after_score"]}],
                       "success_threshold": 1.0, "enable_soft_comparison": True, "validation_threshold": 0.5})
        memories = (response.get("metadata") or {}).get("memory_list") or []
        append(checkpoint, {"task_id":item["task_id"], "response":response,
                            "response_sha256":sha(response), "memory_count":len(memories)})
        append(PROGRESS, {"event":"reme_lifecycle", "arm":name, "task_id":item["task_id"],
                          "output_sha256":sha(memories), "memory_count":len(memories)})


def build_copro(raw: list[dict[str, Any]], attempt: str) -> CoProMemAppWorldAdapter:
    # CoProMem native decomposition remains explicitly LLM-backed; any response
    # that is not valid JSON fails closed rather than creating fallback advice.
    values = env_values()
    ledger = AppendOnlyLedger(LEDGER, HARD_CAP)
    provenance = RUN / "copromem" / attempt / "calls.jsonl"; provenance.parent.mkdir(parents=True, exist_ok=True)
    cache = RUN / "copromem" / "response-cache.jsonl"
    def json_call(*, system_prompt: str, user_prompt: str, max_tokens: int, schema_name: str | None = None, **_: Any) -> dict[str, Any] | None:
        # The decomposer itself specifies the schema in its unchanged prompt.
        # No local repair, fallback, or generic substitute is permitted.
        role = f"copromem_decomposition:{schema_name or 'unknown'}"
        request_digest = sha({"schema_name":schema_name,"system_prompt":system_prompt,"user_prompt":user_prompt,
                              "max_tokens":min(int(max_tokens),1024),"model":"deepseek/deepseek-v4.1-flash",
                              "provider_only":"deepseek","reasoning_effort":"none"})
        if cache.exists():
            for line in cache.read_text(encoding="utf-8").splitlines():
                cached = json.loads(line)
                if cached.get("request_digest") == request_digest:
                    try:
                        parsed, raw, span = extract_copromem_json(schema_name or "", cached["accepted_object"], "stop", False)
                    except (KeyError, StrictJSONError):
                        continue
                    if parsed == cached.get("parsed_object") and raw == cached["accepted_object"] and isinstance(cached.get("object_span"), list):
                        append(provenance,{"schema_name":schema_name,"request_digest":request_digest,"cache_reused":True,
                                           "content_sha256":cached["raw_response_sha256"]})
                        return parsed
        client = LockedOpenAI(api_key=values["OPENROUTER_API_KEY"], ledger=ledger, progress=PROGRESS, role=role)
        result = client.chat.completions.create(model="deepseek/deepseek-v4.1-flash", stream=False,
            max_tokens=min(int(max_tokens), 1024), messages=[{"role":"system","content":system_prompt},
            {"role":"user","content":user_prompt}], temperature=0)
        choice = result.choices[0]; answer = choice.message.content
        kind = classify(answer, choice.finish_reason, bool(choice.message.tool_calls))
        append(provenance,{"schema_name":schema_name,"request_digest":request_digest,"finish_reason":choice.finish_reason,
                           "content_sha256":hashlib.sha256(answer.encode()).hexdigest(),"content_length":len(answer),
                           "tool_call_present":bool(choice.message.tool_calls),"format_classification":kind})
        try:
            parsed, accepted, span = extract_copromem_json(schema_name or "", answer, choice.finish_reason, bool(choice.message.tool_calls))
        except StrictJSONError as exc:
            raise DispatchFailure("CoProMem decomposition response rejected by strict format gate") from exc
        record={"request_digest":request_digest,"schema_name":schema_name,"finish_reason":choice.finish_reason,
                "raw_response_sha256":hashlib.sha256(answer.encode()).hexdigest(),"accepted_object":accepted,
                "object_span":list(span),"parsed_object":parsed}
        append(cache,record)
        append(provenance,{"schema_name":schema_name,"request_digest":request_digest,"cache_reused":False,
                           "accepted_object_sha256":hashlib.sha256(accepted.encode()).hexdigest(),"object_span":list(span)})
        return parsed
    adapter = CoProMemAppWorldAdapter(api_key="configured", model="deepseek/deepseek-v4.1-flash",
        provider_only="deepseek", reasoning_effort="none", llm_json_call=json_call,
        decomposition_call_cap=320)
    for item in raw:
        actions = tuple(m["content"] for m in item["task_history"] if m.get("role") == "assistant")
        task_text = next((m.get("content", "") for m in item["task_history"] if m.get("role") == "user"), "")
        adapter.ingest(RawAcquisitionTrajectory(AcquisitionIdentity(item["task_id"], 0, 0), task_text, "appworld",
                       item["after_score"] == 1.0, actions=actions, task_state={"history_sha256":sha(item["task_history"])}))
    adapter.consolidate(); return adapter


def run_trial(task_id: str, seed: int, trial: int, arm: str, base: str | None, api_key: str,
              ledger: AppendOnlyLedger, all_ids: list[str], injected: str = "") -> tuple[dict[str, Any], Any | None]:
    """Execute the upstream prompt/call/parser/action loop once.

    This mirrors the pinned ``execute`` body solely to supply CoProMem's
    externally retrieved memory.  Every decision-bearing method remains the
    actual upstream agent method: ``prompt_messages``, ``call_llm`` and
    ``extract_code_and_fix_content``.
    """
    key = f"evaluation:{arm}:{task_id}:seed={seed}:trial={trial}"
    journal = safe_journal_path(RUN / "journals", key)
    journal.parent.mkdir(parents=True, exist_ok=True)
    token = CALL_ROLE.set(f"executor:{arm}:{task_id}:seed={seed}:trial={trial}")
    try:
        Agent = load_official_agent(allowed_tasks=all_ids, api_key=api_key, ledger=ledger,
                                    progress=PROGRESS, journal_path=journal, trajectory_id=key)
        use_memory = arm != "no_memory"
        agent = Agent(index=seed, task_ids=[task_id], experiment_name=f"reduced_v2_{arm}",
                      model_name="deepseek/deepseek-v4.1-flash", max_interactions=30, num_trials=1,
                      use_memory=use_memory, memory_base_url=base or "http://127.0.0.1:9/",
                      use_memory_addition=arm == "official_upstream_reme_dynamic",
                      use_memory_deletion=arm == "official_upstream_reme_dynamic")
        with AppWorldProxy(task_id=task_id, experiment_name=f"reduced_v2_{arm}_{seed}_{trial}") as world:
            before = agent.get_reward(world)
            last_prompt_tokens: int | None = None
            previous = [] if not injected else [{"when_to_use": "Retrieved procedural guidance",
                                                  "content": injected}]
            agent.prompt_messages(0, 0, previous, world)
            for _ in range(30):
                try:
                    text = agent.call_llm(agent.history[0][0])
                    last_prompt_tokens = getattr(agent.llm_client.chat.completions,
                        "last_accepted_prompt_tokens", last_prompt_tokens)
                except ContextCeilingTermination as ceiling:
                    # No dispatch occurred. Score the exact current native state
                    # before this trajectory becomes terminal.
                    after = agent.get_reward(world)
                    result = {"task_id":task_id, "seed":seed, "trial":trial, "arm":arm,
                        "before_score":before, "after_score":after, "task_completed":world.task_completed(),
                        "actions":len([m for m in agent.history[0][0] if m["role"] == "assistant"]),
                        "history":agent.history[0][0], "memory_sha256":sha(injected),
                        "termination_reason":"context_ceiling_termination",
                        "last_accepted_prompt_tokens":last_prompt_tokens,
                        "configured_input_token_ceiling":ceiling.ceiling,
                        "next_prompt_token_estimate":ceiling.estimated_prompt_tokens}
                    append(PROGRESS,{"event":"context_ceiling_termination","stage":"evaluation","arm":arm,
                        "task_id":task_id,"seed":seed,"trial":trial,"completed_action_count":result["actions"],
                        "last_accepted_prompt_tokens":last_prompt_tokens,"configured_input_token_ceiling":ceiling.ceiling})
                    return result, (agent if arm == "official_upstream_reme_dynamic" else None)
                code, _ = agent.extract_code_and_fix_content(text)
                agent.history[0][0].append({"role": "assistant", "content": code})
                output = world.execute(code)
                agent.history[0][0].append({"role": "user", "content": "Output:\n```\n" + output + "```\n\n"})
                if world.task_completed(): break
            after = agent.get_reward(world)
            # Fixed is frozen after construction.  Return the official score
            # before any optional dynamic update can execute.
            result = {"task_id":task_id, "seed":seed, "trial":trial, "arm":arm, "before_score":before,
                    "after_score":after, "task_completed":world.task_completed(), "actions":len([m for m in agent.history[0][0] if m["role"] == "assistant"]),
                    "history":agent.history[0][0], "memory_sha256":sha(injected)}
            return result, (agent if arm == "official_upstream_reme_dynamic" else None)
    finally:
        CALL_ROLE.reset(token)


def evaluation(manifest: dict[str, Any], api_key: str, ledger: AppendOnlyLedger,
               fixed: str, dynamic: str, copro: CoProMemAppWorldAdapter) -> None:
    all_ids = manifest["acquisition"]["task_ids"] + manifest["evaluation"]["task_ids"]
    for task_id in manifest["evaluation"]["task_ids"]:
        for trial, seed in enumerate(manifest["evaluation"]["seeds"], 1):
            for arm, base in (("no_memory", None), ("official_upstream_reme_fixed", fixed),
                              ("official_upstream_reme_dynamic", dynamic), ("copromem_v2", None)):
                key = f"evaluation:{arm}:{task_id}:seed={seed}:trial={trial}"
                artifact = RUN / "evaluation" / f"{arm}-{task_id}-{seed}.json"
                if completed(key): continue
                disk_guard()
                injected = ""
                if arm == "copromem_v2":
                    injected = copro.prepare_trial(TrialInput(task_id=task_id, intent="", domain="appworld"), trial)
                result, dynamic_agent = run_trial(task_id, seed, trial, arm, base, api_key, ledger, all_ids, injected)
                write_json(artifact, result)
                mark_completed(key, {"artifact":str(artifact.relative_to(ROOT)),"sha256":sha(result)})
                append(PROGRESS,{"event":"trajectory_complete","stage":"evaluation","task_id":task_id,
                                 "trial":trial,"arm":arm,"score":result["after_score"],
                                 "actions":result["actions"],"history_sha256":sha(result["history"])})
                # The scored trajectory is now durable.  An optional dynamic
                # post-trial update is an independent, non-replayable artifact.
                if dynamic_agent is not None:
                    update_key = f"dynamic-update:{task_id}:seed={seed}:trial={trial}"
                    update_artifact = RUN / "evaluation_updates" / f"{task_id}-{seed}-{trial}.json"
                    try:
                        state = dynamic_post_trial_update(dynamic_agent, result["after_score"],
                            lambda record: append(PROGRESS, {**record, "stage":"evaluation", "task_id":task_id,
                                "seed":seed, "trial":trial, "arm":arm, "trajectory_completed":True}))
                        write_json(update_artifact, {"state":state, "trajectory_key":key})
                    except Exception as exc:
                        write_json(update_artifact, {"state":"failed", "trajectory_key":key,
                            "error_type":type(exc).__name__, "error":str(exc)[:500]})
                        append(PROGRESS,{"event":"dynamic_update_failed","stage":"evaluation", "task_id":task_id,
                            "seed":seed,"trial":trial,"arm":arm,"trajectory_completed":True,
                            "error_type":type(exc).__name__})
                    mark_completed(update_key, {"artifact":str(update_artifact.relative_to(ROOT)), "trajectory_key":key})


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--service-preflight", action="store_true"); args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")); digest = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    expected = (RUN / "manifest.sha256").read_text().strip()
    if digest != expected: raise RuntimeError("frozen reduced_v2 manifest digest mismatch")
    values = env_values()
    if not values.get("OPENROUTER_API_KEY") or not values.get("FLOW_EMBEDDING_API_KEY") or not values.get("FLOW_EMBEDDING_BASE_URL"):
        raise RuntimeError("locked route configuration unavailable")
    disk_guard(); RUN.mkdir(parents=True, exist_ok=True)
    write_json(STATUS, {"state":"running", "pid":os.getpid(), "manifest_sha256":digest,
                        "protocol_size":{"acquisition":6,"evaluation":4,"trials":4,"arms":4},
                        "concurrency":1,"reason":"serial until exact isolation proof exists"})
    append(PROGRESS, {"event":"runner_started", "protocol":"reduced_v2", "manifest_sha256":digest,"pid":os.getpid()})
    # USD35 ledger. Previous protocol records are external immutable artifacts;
    # their settled OpenRouter exposure is carried by one immutable successor
    # record rather than copied/reinterpreted line by line.
    ledger = AppendOnlyLedger(LEDGER, HARD_CAP)
    if not LEDGER.exists() or not LEDGER.read_text(encoding="utf-8").strip():
        ledger.reserve("carry-forward-openrouter", 0.03131748,
                       {"role":"immutable_historical_carry_forward","source":"prior_ledgers"})
        ledger.settle("carry-forward-openrouter", 0.03131748,
                      {"role":"immutable_historical_carry_forward","source":"prior_ledgers"})
    if args.preflight:
        load_official_agent(allowed_tasks=manifest["acquisition"]["task_ids"] + manifest["evaluation"]["task_ids"],
                            api_key=values["OPENROUTER_API_KEY"], ledger=ledger, progress=PROGRESS,
                            journal_path=RUN / "journals" / "preflight.jsonl")
        append(PROGRESS,{"event":"preflight_passed","manifest_sha256":digest})
        write_json(STATUS,{"state":"preflight_passed","pid":os.getpid(),"manifest_sha256":digest})
        return
    if args.service_preflight:
        with reme_services("service-preflight"):
            append(PROGRESS,{"event":"official_reme_service_preflight_passed","manifest_sha256":digest})
        write_json(STATUS,{"state":"service_preflight_passed","pid":os.getpid(),"manifest_sha256":digest})
        return
    try:
        raw = acquisition(manifest, values["OPENROUTER_API_KEY"], ledger)
        attempt = RUN / "lifecycle-successor-attempt-v3.json"
        if not attempt.exists():
            write_json(attempt, {"attempt":"v3", "state":"started", "time_ns":time.time_ns(),
                "input_acquisition_artifact_hashes":[sha(item) for item in raw],
                "predecessor":"lifecycle_successor_v2_failed_after_settled_calls_before_response_checkpoint",
                "label":"exploratory faithful adaptation; successor construction"})
            append(PROGRESS,{"event":"lifecycle_successor_started","attempt":"v3",
                             "replayed_acquisition":False,"input_count":len(raw)})
        # Separate upstream fixed/dynamic services prevent cross-arm state.
        with reme_services("lifecycle-successor-v3") as (fixed, dynamic):
            construct_reme(fixed, raw, "official_upstream_reme_fixed", "v3")
            construct_reme(dynamic, raw, "official_upstream_reme_dynamic", "v3")
            # Evaluation deliberately starts only after both official lifecycle
            # constructions succeed. CoPro construction occurs afterwards.
            copro_attempt = RUN / "copromem-successor-attempt-v3.json"
            if not copro_attempt.exists():
                write_json(copro_attempt,{"attempt":"v3","time_ns":time.time_ns(),
                    "predecessor":"failed_unfinalized_copromem_construction_v2",
                    "input_acquisition_artifact_hashes":[sha(item) for item in raw],
                    "label":"exploratory faithful adaptation; strict JSON format-only successor"})
                append(PROGRESS,{"event":"copromem_successor_started","attempt":"v3","replayed_acquisition":False})
            copro = build_copro(raw, "v3")
            append(PROGRESS,{"event":"lifecycle_ready","copromem_state_sha256":sha(copro.export_state())})
            evaluation(manifest, values["OPENROUTER_API_KEY"], ledger, fixed, dynamic, copro)
        # Mark completion only after both final reports were durably generated.
        subprocess.run([SERVICE_PY, str(REPORT_SCRIPT)], cwd=ROOT,
                       env={**os.environ, "PYTHONPATH":".", "OFFICIAL_PILOT_RUN":str(RUN)}, check=True)
        report, markdown = RUN / "final-report.json", RUN / "FINAL_REPORT.md"
        if not report.exists() or not markdown.exists(): raise RuntimeError("final report post-processing missing")
        report_hash=hashlib.sha256(report.read_bytes()).hexdigest()
        markdown_hash=hashlib.sha256(markdown.read_bytes()).hexdigest()
        append(PROGRESS,{"event":"final_reports_durable","final_report_sha256":report_hash,
                         "markdown_sha256":markdown_hash})
        write_json(STATUS,{"state":"completed","pid":os.getpid(),"manifest_sha256":digest,
                           "final_report":str(report),"final_report_sha256":report_hash,
                           "markdown_report_sha256":markdown_hash})
    except BaseException as exc:
        write_json(STATUS,{"state":"failed","pid":os.getpid(),"manifest_sha256":digest,
                           "error_type":type(exc).__name__,"error":str(exc)[:256]})
        append(PROGRESS,{"event":"runner_failed","error_type":type(exc).__name__})
        raise

if __name__ == "__main__": main()
