from __future__ import annotations

import json
import importlib.util
from pathlib import Path

import pytest
from types import SimpleNamespace

from copromem.experiments.reme_copromem.prompt_memory import render_executor_memory_slot
from copromem.integrations.reasoning_bank.appworld import ReasoningBank, sha256
from copromem.integrations.reasoning_bank.checkpoints import CheckpointPrefix, ReasoningBankDynamicCheckpoints
from copromem.integrations.reasoning_bank.dynamic_runtime import ReasoningBankDynamicRuntime
import copromem.integrations.reasoning_bank.dynamic_runtime as dynamic_runtime_module
from copromem.integrations.reasoning_bank.lifecycle import ReasoningBankLifecycle
from copromem.integrations.reasoning_bank.recovery_admission import (
    admit, build_spec, portable_source_run, resolve_source_run,
)
from copromem.integrations.reasoning_bank.retrieval_provenance import ContentAddressedStore


SOURCE = Path("E:/Project/AAMAS/reasoningbank-appworld-artifacts/reasoningbank_appworld_engineering_014_clean_exposed_restart")


def test_recovery_source_locator_is_portable_between_windows_and_wsl(monkeypatch: pytest.MonkeyPatch):
    assert portable_source_run(r"E:\Project\AAMAS\run") == "E:/Project/AAMAS/run"
    assert portable_source_run("/mnt/e/Project/AAMAS/run") == "E:/Project/AAMAS/run"
    # Native test host resolves the canonical drive locator without embedding
    # a worktree-relative Windows string in the frozen identity.
    assert portable_source_run(resolve_source_run("E:/Project/AAMAS/run")) == "E:/Project/AAMAS/run"


def _real_spec():
    if not SOURCE.is_dir():
        pytest.skip("immutable Engineering 014 evidence is unavailable")
    manifest = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))
    schedule = [(arm, task, trial, int(seed))
                for task in manifest["evaluation"]["task_ids"]
                for arm in manifest["arms"]
                for trial, seed in enumerate(manifest["evaluation"]["seeds"], 1)]
    return manifest, schedule, build_spec(SOURCE, imported_keys=schedule[:11], pending_key=schedule[11], checkpoint_count=5)


def test_real_admission_retrieval_seals_exact_prompt_without_embedding(tmp_path: Path):
    manifest, _schedule, admission = _real_spec()
    dynamic_ids = [f"evaluation:reasoningbank_dynamic:{task}:trial={trial}:seed={seed}"
                   for task in manifest["evaluation"]["task_ids"]
                   for trial, seed in enumerate(manifest["evaluation"]["seeds"], 1)]
    prefix = CheckpointPrefix.from_source(
        root=SOURCE / "reasoningbank-dynamic-checkpoints", expected_trajectory_ids=dynamic_ids,
        ledger_path=SOURCE / "ledger.jsonl", count=5,
        initial_bank=ReasoningBank.restore(manifest["initial_bank"]),
    )
    manager = ReasoningBankDynamicCheckpoints(
        root=tmp_path / "checkpoints", expected_trajectory_ids=dynamic_ids,
        ledger_path=tmp_path / "ledger.jsonl", prefix=prefix,
    )
    calls = {"embedding": 0}
    def forbidden_embedder(*_args, **_kwargs):
        calls["embedding"] += 1
        raise AssertionError("recovery retrieval attempted an embedding call")
    lifecycle = ReasoningBankLifecycle(
        bank=ReasoningBank.restore(prefix.restored_bank.state()), embedder=forbidden_embedder,
        judge=lambda *_: (_ for _ in ()).throw(AssertionError("judge called")),
        extractor=lambda *_: (_ for _ in ()).throw(AssertionError("extractor called")),
    )
    runtime = ReasoningBankDynamicRuntime(
        lifecycle=lifecycle, initial_bank=ReasoningBank.restore(manifest["initial_bank"]),
        checkpoints=manager, run_root=tmp_path, registry_sha256="c" * 64,
    )
    pending = admission["pending"]
    source_record = json.loads((SOURCE / pending["source_relative"]).read_text(encoding="utf-8"))
    source_store = ContentAddressedStore(SOURCE / "reasoningbank-retrieval-objects")
    instruction = source_store.load_text(source_record["query"]["object"])
    key = admission["next_key"]
    identity = {
        "trajectory_id": f"evaluation:{key['arm']}:{key['task_id']}:trial={key['trial_id']}:seed={key['seed']}",
        **key, "benchmark": "appworld", "manifest_sha256": "a" * 64,
        "runtime_identity_sha256": "b" * 64, "registry_sha256": "c" * 64,
    }
    path = tmp_path / "retrieval.json"
    guidance = runtime.admission_precomputed_retrieval_callback(path, admission=admission, identity=identity)(instruction, "appworld", {})
    messages = [{"role": "user", "content": render_executor_memory_slot(guidance)}]
    runtime.admission_prompt_binding_callback(path, admission=admission, identity=identity)(messages, guidance)
    receipt = runtime._admission_receipt(path, admission, require_prompt_binding=True)
    assert receipt.rendered_guidance == guidance
    assert receipt.score_hex[0] == "0x1.0000000000001p+0"
    assert receipt.embedding_request_prohibited is True
    assert calls["embedding"] == 0
    row = json.loads(path.read_text(encoding="utf-8"))
    binding = json.loads(path.with_suffix(path.suffix + ".prompt-binding.json").read_text(encoding="utf-8"))
    assert binding["receipt_sha256"] == receipt.receipt_sha256
    assert binding["callback_guidance_sha256"] == sha256(guidance)
    assert row["prompt_binding"]["binding_sha256"] == binding["binding_sha256"]


def test_real_admission_retrieval_rejects_changed_candidate(tmp_path: Path):
    manifest, _schedule, admission = _real_spec()
    altered = json.loads(json.dumps(admission))
    altered["pending"]["candidates"][0]["score"]["float64_hex"] = "0x1.0000000000000p+0"
    # The callback must reject admission/source disagreement before any provider boundary.
    dynamic_ids = [f"evaluation:reasoningbank_dynamic:{task}:trial={trial}:seed={seed}"
                   for task in manifest["evaluation"]["task_ids"]
                   for trial, seed in enumerate(manifest["evaluation"]["seeds"], 1)]
    recovered = CheckpointPrefix.from_source(
        root=SOURCE / "reasoningbank-dynamic-checkpoints", expected_trajectory_ids=dynamic_ids,
        ledger_path=SOURCE / "ledger.jsonl", count=5,
        initial_bank=ReasoningBank.restore(manifest["initial_bank"]),
    )
    initial_bank = ReasoningBank.restore(manifest["initial_bank"])
    bank = ReasoningBank.restore(recovered.restored_bank.state())
    manager = ReasoningBankDynamicCheckpoints(root=tmp_path / "cp", expected_trajectory_ids=["x"], ledger_path=tmp_path / "ledger")
    runtime = ReasoningBankDynamicRuntime(
        lifecycle=ReasoningBankLifecycle(bank=bank, embedder=lambda *_: (_ for _ in ()).throw(AssertionError("embed")),
                                         judge=lambda *_: None, extractor=lambda *_: None),
        initial_bank=bank, checkpoints=manager, run_root=tmp_path, registry_sha256="c" * 64,
    )
    key = altered["next_key"]
    identity = {"trajectory_id": "x", **key, "benchmark": "appworld", "manifest_sha256": "a" * 64,
                "runtime_identity_sha256": "b" * 64, "registry_sha256": "c" * 64}
    source_record = json.loads((SOURCE / altered["pending"]["source_relative"]).read_text(encoding="utf-8"))
    instruction = ContentAddressedStore(SOURCE / "reasoningbank-retrieval-objects").load_text(source_record["query"]["object"])
    with pytest.raises(RuntimeError, match="reconstruction differs"):
        runtime.admission_precomputed_retrieval_callback(tmp_path / "r.json", admission=altered, identity=identity)(instruction, "appworld", {})


def test_runner_summary_accounts_for_real_e014_prefix_without_arm_cost(tmp_path: Path):
    source_manifest, _schedule, admission = _real_spec()
    runner_path = Path(__file__).parents[2] / "scripts" / "run_reasoningbank_appworld_engineering.py"
    module_spec = importlib.util.spec_from_file_location("reasoningbank_admission_runner", runner_path)
    assert module_spec and module_spec.loader
    runner = importlib.util.module_from_spec(module_spec); module_spec.loader.exec_module(runner)
    manifest = dict(source_manifest)
    manifest["recovery_admission_spec"] = admission
    manifest["historical_infrastructure_exposure_usd"] = .5
    manifest["historical_carry_forward_id"] = runner.HISTORICAL_CARRY_ID
    admit(tmp_path, spec=admission)
    rows = [
        {"event": "reserve", "id": runner.HISTORICAL_CARRY_ID, "role": "historical_carry_forward", "usd": .5},
        {"event": "settle", "id": runner.HISTORICAL_CARRY_ID, "role": "historical_carry_forward", "usd": .5},
    ]
    (tmp_path / "ledger.jsonl").write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")
    runner._summary(tmp_path, manifest, "recovery_admitted")
    summary = json.loads((tmp_path / "live-summary.json").read_text(encoding="utf-8"))
    assert summary["completed"] == 11 and summary["expected"] == 12
    assert summary["imported_completed"] == 11 and summary["successor_completed"] == 0
    assert summary["referenced_checkpoints"] == 5 and summary["native_checkpoints"] == 0
    assert sum(int(value["Completed"]) for value in summary["arms"].values()) == 11
    assert all(float(value["TotalCost"]) == 0 for value in summary["arms"].values())
    material = runner._runtime_identity_material(manifest)
    assert material["recovery_admission_spec_sha256"] == admission["recovery_spec_sha256"]


def test_precomputed_receipt_crosses_strict_post_score_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    manifest, _schedule, admission = _real_spec()
    (tmp_path / "manifest.json").write_text(json.dumps({"fixture": True}, sort_keys=True), encoding="utf-8")
    manifest_sha = __import__("hashlib").sha256((tmp_path / "manifest.json").read_bytes()).hexdigest()
    pending = admission["pending"]; key = admission["next_key"]
    source_record = json.loads((SOURCE / pending["source_relative"]).read_text(encoding="utf-8"))
    instruction = ContentAddressedStore(SOURCE / "reasoningbank-retrieval-objects").load_text(source_record["query"]["object"])
    dynamic_ids = [f"evaluation:reasoningbank_dynamic:{task}:trial={trial}:seed={seed}"
                   for task in manifest["evaluation"]["task_ids"]
                   for trial, seed in enumerate(manifest["evaluation"]["seeds"], 1)]
    recovered = CheckpointPrefix.from_source(
        root=SOURCE / "reasoningbank-dynamic-checkpoints", expected_trajectory_ids=dynamic_ids,
        ledger_path=SOURCE / "ledger.jsonl", count=5,
        initial_bank=ReasoningBank.restore(manifest["initial_bank"]),
    )
    initial_bank = ReasoningBank.restore(manifest["initial_bank"])
    bank = ReasoningBank.restore(recovered.restored_bank.state())
    # The strict boundary is tested without invoking judge/extractor providers.
    captured = {}
    class Checkpoints:
        def update(self, **kwargs):
            captured.update(kwargs)
            return "checkpoint-0006"
    lifecycle = ReasoningBankLifecycle(
        bank=ReasoningBank.restore(bank.state()), embedder=lambda *_: (_ for _ in ()).throw(AssertionError("embed")),
        judge=lambda *_: (_ for _ in ()).throw(AssertionError("judge")),
        extractor=lambda *_: (_ for _ in ()).throw(AssertionError("extractor")),
    )
    runtime = ReasoningBankDynamicRuntime(
        lifecycle=lifecycle, initial_bank=initial_bank, checkpoints=Checkpoints(), run_root=tmp_path,
        registry_sha256="c" * 64, runtime_identity_record_sha256="d" * 64,
    )
    identity = {
        "trajectory_id": f"evaluation:{key['arm']}:{key['task_id']}:trial={key['trial_id']}:seed={key['seed']}",
        **key, "benchmark": "appworld", "manifest_sha256": manifest_sha,
        "runtime_identity_sha256": "b" * 64, "registry_sha256": "c" * 64,
    }
    retrieval_path = tmp_path / "retrievals" / key["task_id"] / f"{key['arm']}-trial-{key['trial_id']}.json"
    guidance = runtime.admission_precomputed_retrieval_callback(retrieval_path, admission=admission, identity=identity)(instruction, "appworld", {})
    messages = [{"role": "user", "content": render_executor_memory_slot(guidance)}]
    runtime.admission_prompt_binding_callback(retrieval_path, admission=admission, identity=identity)(messages, guidance)
    binding = json.loads(retrieval_path.with_suffix(retrieval_path.suffix + ".prompt-binding.json").read_text(encoding="utf-8"))
    artifact = {
        "trajectory_id": identity["trajectory_id"], "task_id": key["task_id"], "arm": key["arm"],
        "trial_id": key["trial_id"], "seed": key["seed"], "runtime_identity_sha256": "b" * 64,
        "runtime_identity_record_sha256": "d" * 64, "execution_evidence_registry_sha256": "c" * 64,
        "injected_memory_sha256": sha256(guidance), "injected_memory_nonempty": True,
        "initial_prompt_messages_sha256": binding["initial_prompt_messages_sha256"],
        "model_visible_prompt_sha256": "e" * 64, "model_visible_memory_binding_sha256": "f" * 64,
        "execution_evidence_sha256": "1" * 64, "history_sha256": "2" * 64,
        "history": [{"role": "user", "content": "fixture"}],
    }
    artifact_path = tmp_path / "artifacts" / key["task_id"] / key["arm"] / f"trial-{key['trial_id']}.json"
    artifact_path.parent.mkdir(parents=True); artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    monkeypatch.setattr(dynamic_runtime_module, "validate_execution_evidence", lambda *_args, **_kwargs: None)
    result = runtime.strict_post_score_callback(retrieval_path, admission=admission)(
        None, artifact, SimpleNamespace(task=SimpleNamespace(instruction=instruction)))
    assert result == "checkpoint-0006"
    assert captured["trajectory"] == artifact
    assert captured["retrieval_record"]["execution_binding"]["injected_memory_sha256"] == sha256(guidance)
