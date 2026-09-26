"""Failure-informed, exact-ID-held-out exploratory pilot.

This program is intentionally separate from the completed confirmatory run.
It never mutates its source acquisition artifacts and it cannot silently turn
the observed 0/48 acquisition outcome into a success pool.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, "src")

from copromem.appworld_comparison_adapter import AcquisitionIdentity, CoProMemAppWorldAdapter, RawAcquisitionTrajectory, TrialInput
from copromem.appworld_live_smoke import ARMS, LOCKED_MODEL, LockedOpenRouterTransport, UnifiedSuccessorRunner
from copromem.checkpoints import RunStore, canonical, digest
from copromem.exploratory_successor_ledger import ExploratorySuccessorLedger
from copromem.reme_paper_lifecycle import ReMeMemory, ReMePaperLifecycle


SOURCE_ROOT = Path("artifacts/research/reme_copromem_comparison/openrouter_successor_exact_id_pilot")
ROOT = Path("artifacts/research/reme_copromem_comparison/openrouter_failure_informed_exploratory_pilot")
SOURCE_MANIFEST = Path("research/OPENROUTER_SUCCESSOR_EXACT_ID_MANIFEST.json")
WORKER = "/mnt/e/Project/AAMAS/COPROMEM/research/containers/appworld/real_worker.py"
PYTHON = "/home/xiqhq/copromem-appworld/venv/bin/python"
PROMPT = "Use only documented prebound `apis`; do not import, reflect, or guess endpoint names. Execute and verify the task within the action budget."
TOOLS = {"type": "function", "function": {"name": "execute_python", "description": "Execute one documented AppWorld Python action.", "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"], "additionalProperties": False}}}
DECOMP_TOOL = {"type": "function", "function": {"name": "return_decomposition_json", "description": "Return decomposition JSON.", "parameters": {"type": "object", "properties": {"result": {"type": "object"}}, "required": ["result"], "additionalProperties": False}}}
HISTORICAL_ROOTS = [
    Path("artifacts/research/reme_copromem_comparison/acquisition_readiness"),
    Path("artifacts/research/reme_copromem_comparison/corrected_direct_deepseek_smoke"),
    Path("artifacts/research/reme_copromem_comparison/direct_deepseek_successor_smoke"),
    Path("artifacts/research/reme_copromem_comparison/diverse_acquisition"),
    Path("artifacts/research/reme_copromem_comparison/final_acquisition_readiness"),
    Path("artifacts/research/reme_copromem_comparison/openrouter_brokered_smoke"),
    Path("artifacts/research/reme_copromem_comparison/openrouter_deepseek_successor_canary"),
    Path("artifacts/research/reme_copromem_comparison/openrouter_deepseek_successor_canary_corrected"),
    SOURCE_ROOT,
]
HISTORICAL_ATTEMPTS = 1101
# The protocol displays this to eight decimals; the ledger retains the exact
# sum of immutable JSON amounts so its provenance check is not rounded.
HISTORICAL_EXPOSURE = 0.777529779
EVALUATION_CALLS = 30 * 2 * 4 * 30
COPROMEM_DECOMPOSITION_CALLS = 320
PER_CALL_USD = 0.003072
NEW_RESERVED_USD = (EVALUATION_CALLS + COPROMEM_DECOMPOSITION_CALLS) * PER_CALL_USD
CONTINGENCY_USD = NEW_RESERVED_USD * 0.15


def api_key() -> str:
    value = os.environ.get("OPENROUTER_API_KEY", "")
    if value:
        return value
    dotenv = Path(".env")
    if dotenv.exists():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip().strip("'\"")
    return ""


class Worker:
    def start(self, task: str, phase: str) -> Mapping[str, Any]:
        process = subprocess.Popen(
            ["wsl.exe", "-d", "Ubuntu", "--cd", "/home/xiqhq/copromem-appworld", "--", "env", f"APPWORLD_ALLOWED_TASKS={task}", PYTHON, WORKER],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
        )
        def send(value: Mapping[str, Any]) -> Mapping[str, Any]:
            assert process.stdin is not None and process.stdout is not None
            process.stdin.write(json.dumps(value) + "\n")
            process.stdin.flush()
            line = process.stdout.readline()
            if not line:
                raise RuntimeError("native AppWorld worker ended")
            return json.loads(line)
        world = dict(send({"op": "start", "task_id": task, "experiment_name": "failure_informed_exploratory"}))
        world["_send"], world["_process"] = send, process
        return world

    def act(self, world: Mapping[str, Any], code: str) -> Mapping[str, Any]:
        return world["_send"]({"op": "action", "code": code})

    def finish(self, world: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            return world["_send"]({"op": "finish"})
        finally:
            world["_process"].wait(timeout=15)


def acquisition_rows() -> list[dict[str, Any]]:
    rows = []
    for path in sorted((SOURCE_ROOT / "acquisition_scores").glob("*.json")):
        score = json.loads(path.read_text(encoding="utf-8"))
        match = re.fullmatch(r"(.+)--seed-(\d+)--trajectory-(\d+)", path.stem)
        if match is None:
            raise RuntimeError(f"unparseable immutable acquisition score key: {path.name}")
        filename_task, filename_seed, _ = match.groups()
        task_id = score.get("task_id", filename_task)
        seed = int(score.get("seed", filename_seed))
        if task_id != filename_task or seed != int(filename_seed):
            raise RuntimeError(f"immutable acquisition score identity disagrees with filename: {path.name}")
        rows.append({
            "task_id": task_id, "seed": seed,
            "official_success": bool(score["official_score"]["success"]),
            "score_artifact_sha256": __import__("hashlib").sha256(path.read_bytes()).hexdigest(),
            "trace_sha256": score.get("trace_sha256", ""),
            "score": score["official_score"],
        })
    if len(rows) != 48 or any(row["official_success"] for row in rows):
        raise RuntimeError("source acquisition pool is not the immutable observed 0/48 pool")
    return rows


def freeze_manifest(store: RunStore) -> dict[str, Any]:
    source = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    rows = acquisition_rows()
    manifest = {
        "version": "failure-informed-exploratory-v1",
        "status": "frozen_before_evaluation_payload_access",
        "interpretation": "Created after observing 0/48 acquisition successes. Exploratory only; no confirmatory efficacy, superiority, task-family, template-level, or benchmark-wide generalization claim.",
        "source_confirmatory_manifest_sha256": __import__("hashlib").sha256(SOURCE_MANIFEST.read_bytes()).hexdigest(),
        "source_confirmatory_terminal_sha256": __import__("hashlib").sha256((SOURCE_ROOT / "pilot_terminal" / "acquisition_gate.json").read_bytes()).hexdigest(),
        "source_acquisition_pool": rows,
        "source_acquisition_seeds": source["acquisition"]["seeds"],
        "evaluation": {"task_ids": source["evaluation"]["task_ids"], "seeds": source["evaluation"]["seeds"], "exact_id_holdout_only": True},
        "arms": list(ARMS), "max_actions": 30, "max_completion_tokens": 1024,
        "route": {"endpoint": "https://openrouter.ai/api/v1/chat/completions", "model": LOCKED_MODEL, "provider_only": ["deepseek"], "allow_fallbacks": False, "reasoning_effort": "none", "stream": False, "tool_choice": "auto", "parallel_tools": "one declared tool plus exactly-one-call response gate"},
        "parity": {"prompt_sha256": digest(PROMPT), "tool_schema_sha256": digest(TOOLS), "memory_is_only_arm_specific_executor_input": True, "official_scorer": "native AppWorld worker"},
        "lifecycle": {"reme_fixed": "faithful adaptation; only acquired successful procedural memories; empty when no successes", "reme_dynamic": "faithful adaptation; independent seed streams with post-evaluation failure-aware utility/frequency update", "copromem_v2": "failure episodes retained; defaults disabled; native admission/consolidation; empty retrieval permitted"},
        "analysis": {"unit": "task x seed paired arm outcome", "estimands": ["paired success-rate differences versus No Memory", "task-clustered bootstrap confidence intervals"], "not_confirmatory": True},
        "budget": {"historical_records": HISTORICAL_ATTEMPTS, "historical_exposure_usd": 0.77752978, "evaluation_calls": EVALUATION_CALLS, "copromem_decomposition_calls": COPROMEM_DECOMPOSITION_CALLS, "reme_lifecycle_calls": 0, "new_reserved_usd": NEW_RESERVED_USD, "non_dispatchable_contingency_usd": CONTINGENCY_USD, "all_in_usd": 27.344185779999997, "absolute_cap_usd": 35.0},
    }
    store.write("manifest", "failure_informed_exploratory_v1", manifest)
    return manifest


class FailureInformedLifecycle:
    def __init__(self, *, store: RunStore, transport: LockedOpenRouterTransport, manifest: Mapping[str, Any]) -> None:
        self.store, self.transport, self.manifest = store, transport, manifest
        self.raw = self._load_raw_pool()
        # All 48 source episodes are failures. Fixed receives no acquired
        # procedure; dynamic begins with the same empty acquired pool and may
        # update only from evaluation outcomes.
        self.fixed = ReMePaperLifecycle([], dynamic=False)
        self.dynamic = ReMePaperLifecycle([], dynamic=True)
        self.serial = 0
        self.copro = CoProMemAppWorldAdapter(
            api_key=api_key(), model=LOCKED_MODEL, provider_only="deepseek", reasoning_effort="none",
            llm_json_call=self._decompose, decomposition_call_cap=COPROMEM_DECOMPOSITION_CALLS,
        )

    def _load_raw_pool(self) -> list[RawAcquisitionTrajectory]:
        out = []
        for row in self.manifest["source_acquisition_pool"]:
            index = self._seed_index(row["seed"])
            ref = f"{row['task_id']}--seed-{row['seed']}--trajectory-{index}"
            context = RunStore(SOURCE_ROOT).read("trajectory_context", ref + "--acquisition--shared") or {}
            action_paths = sorted((SOURCE_ROOT / "acquisition_actions").glob(ref + "--*.json"))
            actions = tuple((json.loads(path.read_text(encoding="utf-8"))).get("code", "") for path in action_paths)
            out.append(RawAcquisitionTrajectory(
                AcquisitionIdentity(row["task_id"], row["seed"], index),
                str(context.get("instruction", row["task_id"])), "appworld", bool(row["official_success"]), actions,
                {"source_trace_sha256": row["trace_sha256"], "source_score_artifact_sha256": row["score_artifact_sha256"]},
            ))
        return out

    def _seed_index(self, seed: int) -> int:
        return list(self.manifest["source_acquisition_seeds"]).index(seed)

    def _decompose(self, *, system_prompt: str, user_prompt: str, max_tokens: int, schema_name: str | None = None) -> dict[str, Any]:
        self.serial += 1
        outcome = self.transport.dispatch(
            key=f"lifecycle--copromem-decomposition--{self.serial}",
            metadata={"phase": "lifecycle", "role": "copromem_decomposition", "arm": "copromem_v2", "iteration": self.serial, "model": LOCKED_MODEL},
            prompt=system_prompt + "\n" + user_prompt, tools=DECOMP_TOOL, upper_usd=PER_CALL_USD,
        )
        return dict(outcome.output["result"])

    def construct(self) -> Mapping[str, str]:
        completed = [self.store.read("lifecycle_outputs", arm) for arm in ("reme_fixed", "reme_dynamic", "copromem_v2")]
        if all(completed):
            copro_payload = completed[2]["payload"]
            self.copro.load_state(copro_payload["state"])
            return {"reme_fixed": "", "reme_dynamic": "", "copromem_v2": ""}
        progress = sorted((self.store.root / "lifecycle_progress").glob("*.json")) if self.store.root else []
        start_at = 0
        if progress:
            latest = json.loads(progress[-1].read_text(encoding="utf-8"))
            self.copro.load_state(latest["copromem_state"])
            start_at = int(latest["source_index"]) + 1
            self.serial = int(latest["decomposition_calls"])
        # Each source episode checkpoints the complete native CoProMem state.
        # A resumed process restores the last checkpoint instead of replaying a
        # completed decomposition or episode record.
        for index, trajectory in enumerate(self.raw[start_at:], start=start_at):
            self.copro.ingest(trajectory)
            self.store.write("lifecycle_progress", f"{index:03d}", {"source_index": index, "source_identity": trajectory.identity.value, "decomposition_calls": self.serial, "copromem_state": self.copro.export_state()})
        self.copro.consolidate()
        payloads = {
            "reme_fixed": {"method": "reme_fixed_faithful_adaptation", "source_pool_sha256": digest(self.manifest["source_acquisition_pool"]), "successful_source_episodes": 0, "failure_source_episodes": len(self.raw), "memory_text": "", "memory_ids": []},
            "reme_dynamic": {"method": "reme_dynamic_faithful_adaptation", "source_pool_sha256": digest(self.manifest["source_acquisition_pool"]), "successful_source_episodes": 0, "failure_source_episodes": len(self.raw), "memory_text": "", "memory_ids": []},
            "copromem_v2": {"method": "copromem_v2", "source_pool_sha256": digest(self.manifest["source_acquisition_pool"]), "successful_source_episodes": 0, "failure_source_episodes": len(self.raw), "state": self.copro.export_state()},
        }
        for arm, payload in payloads.items():
            self.store.write("lifecycle_outputs", arm, {"sha256": digest(payload), "payload": payload})
        # Fixed/dynamic must remain truly empty rather than substitute generic
        # failure text. CoProMem retrieval is performed lazily once per trial.
        return {"reme_fixed": "", "reme_dynamic": "", "copromem_v2": ""}

    def memory_for(self, *, task_id: str, seed: int, arm: str, fallback: str) -> str:
        key = f"{task_id}--seed-{seed}--{arm}"
        prior = self.store.read("exploratory_memory_inputs", key)
        if prior is not None:
            return str(prior["memory_text"])
        if arm == "no_memory":
            memory = ""
        elif arm in {"reme_fixed", "reme_dynamic"}:
            memory = ""
        elif arm == "copromem_v2":
            trial_index = self.manifest["evaluation"]["task_ids"].index(task_id) * len(self.manifest["evaluation"]["seeds"]) + self.manifest["evaluation"]["seeds"].index(seed)
            memory = self.copro.prepare_trial(TrialInput(task_id, task_id, "appworld", base_prompt=PROMPT, tool_spec=TOOLS), trial_index)
        else:
            raise ValueError(f"unknown arm: {arm}")
        self.store.write("exploratory_memory_inputs", key, {"arm": arm, "task_id": task_id, "seed": seed, "memory_text": memory, "memory_sha256": digest(memory), "source_pool_sha256": digest(self.manifest["source_acquisition_pool"]), "empty": not bool(memory.strip())})
        return memory

    def after_trial(self, *, task_id: str, seed: int, arm: str, result: Mapping[str, Any]) -> None:
        if arm != "reme_dynamic":
            return
        stream = self.manifest["evaluation"]["seeds"].index(seed)
        state = self.dynamic.state_for_trial_stream(stream)
        retrieved = list(state.memories)
        self.dynamic.after_evaluation(stream=stream, retrieved_ids=retrieved, success=bool((result.get("official_score") or {}).get("success")), validated_addition=None)
        self.store.write("exploratory_dynamic_updates", f"{task_id}--seed-{seed}", {"task_id": task_id, "seed": seed, "retrieved_ids": retrieved, "official_success": bool((result.get("official_score") or {}).get("success")), "state_sha256": digest({key: vars(value) for key, value in self.dynamic.state_for_trial_stream(stream).memories.items()})})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze-only", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    store = RunStore(ROOT)
    manifest = freeze_manifest(store)
    if args.freeze_only:
        print(json.dumps({"status": "frozen_before_evaluation_payload_access", "manifest_sha256": digest(manifest)}))
        return
    if not api_key():
        raise RuntimeError("OPENROUTER_API_KEY unavailable")
    if shutil.disk_usage("C:\\").free < 10 * 1024**3:
        raise RuntimeError("C storage floor breached")
    ledger = ExploratorySuccessorLedger(store, historical_roots=HISTORICAL_ROOTS, expected_historical_attempts=HISTORICAL_ATTEMPTS, expected_historical_exposure=HISTORICAL_EXPOSURE, max_new_attempts=EVALUATION_CALLS + COPROMEM_DECOMPOSITION_CALLS, max_new_reserved_usd=NEW_RESERVED_USD, max_usd=35.0)
    if args.preflight_only:
        print(json.dumps({"status": "preflight_passed", "historical_attempts": ledger.attempts_used, "historical_exposure_usd": ledger.charged_or_reserved, "new_reserved_envelope_usd": NEW_RESERVED_USD, "non_dispatchable_contingency_usd": CONTINGENCY_USD, "all_in_bound_usd": HISTORICAL_EXPOSURE + NEW_RESERVED_USD + CONTINGENCY_USD}))
        return
    transport = LockedOpenRouterTransport(api_key=api_key(), ledger=ledger)
    lifecycle = FailureInformedLifecycle(store=store, transport=transport, manifest=manifest)
    memories = lifecycle.construct()
    worker = Worker()
    runner = UnifiedSuccessorRunner(store=store, transport=transport, start_world=worker.start, act=worker.act, finish=worker.finish, tools=TOOLS, base_system_prompt=PROMPT)
    evaluation = runner.run_evaluation(manifest, memories, lifecycle)
    store.write("pilot_terminal", "complete", {"status": "exploratory_complete", "evaluation_count": len(evaluation), "ledger_charged_or_reserved_usd": ledger.charged_or_reserved})
    print(json.dumps({"status": "exploratory_complete", "evaluation_count": len(evaluation), "ledger_charged_or_reserved_usd": ledger.charged_or_reserved}))


if __name__ == "__main__":
    main()
