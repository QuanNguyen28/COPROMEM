from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


def _runner():
    path = Path(__file__).parents[2] / "scripts" / "run_reasoningbank_appworld_engineering.py"
    spec = importlib.util.spec_from_file_location("reasoningbank_engineering_runner", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def _python_runtime() -> dict:
    return {"version": "reasoningbank-appworld-python-runtime-v1", "python_executable": "/venv/bin/python",
            "python_version": "3.12.3", "python_prefix": "/venv", "python_base_prefix": "/usr",
            "ray_version": "2.58.0", "appworld_version": "0.1.3.post1", "dependency_set_sha256": "a" * 64,
            "appworld_react_agent_sha256": "b" * 64, "appworld_module_sha256": "c" * 64,
            "entrypoint_sha256": "d" * 64,
            "imports": ["ray", "appworld", "appworld_react_agent", "copromem.experiments.reme_copromem.runner", "reasoningbank_entrypoint"],
            "runtime_identity_sha256": "e" * 64}


def test_prepare_freezes_the_actual_shared_backbone_and_embedding_path(monkeypatch, tmp_path):
    runner = _runner()
    inventory = tmp_path / "public-dev.json"
    inventory.write_text(json.dumps({"split": "dev", "public_only": True, "tasks": [
        {"task_id": "aaaaaaa_1", "instruction": "List top 3 indie songs", "app_descriptions": {}},
        {"task_id": "aaaaaaa_2", "instruction": "List top 4 rock songs", "app_descriptions": {}},
        {"task_id": "bbbbbbb_1", "instruction": "Create a note for tomorrow", "app_descriptions": {}},
    ]}), encoding="utf-8")
    monkeypatch.setenv("REASONINGBANK_PUBLIC_DEV_DESCRIPTORS", str(inventory))
    monkeypatch.setattr(runner, "_hard_exposed_task_ids", lambda: (set(), {}))
    monkeypatch.setattr(runner, "_capture_python_runtime_identity", _python_runtime)
    run = tmp_path / "run"; runner.prepare(run)
    manifest = json.loads((run / "template.json").read_text(encoding="utf-8"))
    assert manifest["evaluation"]["expected_trajectories"] == 12
    assert manifest["execution"]["executor_temperature"] == .7
    assert manifest["execution"]["judge_temperature"] == 0.0
    assert manifest["execution"]["extractor_temperature"] == 1.0
    assert manifest["embedding"] == {"model": "openai/text-embedding-3-small", "provider": "azure",
                                     "transport": "OpenRouter", "dimensions": 1024, "encoding_format": "float",
                                     "provider_fallback": False, "normalization": "unit_l2_before_cosine",
                                     "transport_identity": "copromem.integrations.reme.transport.LockedEmbeddings"}
    assert manifest["budget"]["call_limits"] == {"executor": 360, "reasoningbank_judge": 6,
                                                    "reasoningbank_extraction": 6, "reasoningbank_embedding": 12}
    assert manifest["allocation"]["payloads_opened"] is False
    assert manifest["allocation"]["test_normal_used"] is False


def test_prepare_freezes_separate_historical_infrastructure_exposure(monkeypatch, tmp_path):
    runner = _runner()
    inventory = tmp_path / "public-dev.json"
    inventory.write_text(json.dumps({"split": "dev", "public_only": True, "tasks": [
        {"task_id": "aaaaaaa_1", "instruction": "List top 3 indie songs", "app_descriptions": {}},
        {"task_id": "aaaaaaa_2", "instruction": "List top 4 rock songs", "app_descriptions": {}},
        {"task_id": "bbbbbbb_1", "instruction": "Create a note for tomorrow", "app_descriptions": {}},
    ]}), encoding="utf-8")
    monkeypatch.setenv("REASONINGBANK_PUBLIC_DEV_DESCRIPTORS", str(inventory))
    monkeypatch.setenv("REASONINGBANK_HISTORICAL_EXPOSURE_USD", "0.020932692")
    monkeypatch.setattr(runner, "_hard_exposed_task_ids", lambda: (set(), {}))
    monkeypatch.setattr(runner, "_capture_python_runtime_identity", _python_runtime)
    run = tmp_path / "run"; runner.prepare(run)
    manifest = json.loads((run / "template.json").read_text(encoding="utf-8"))
    assert manifest["historical_infrastructure_exposure_usd"] == 0.020932692
    assert manifest["budget"]["historical_exposure_usd"] == 0.020932692
    assert manifest["budget"]["all_in_usd"] == pytest.approx(manifest["budget"]["dispatchable_usd"]
                                                                + manifest["budget"]["contingency_usd"] + .020932692)


def test_prepare_keeps_previous_engineering_allocation_out_of_successor(monkeypatch, tmp_path):
    runner = _runner()
    inventory = tmp_path / "public-dev.json"
    inventory.write_text(json.dumps({"split": "dev", "public_only": True, "tasks": [
        {"task_id": "aaaaaaa_1", "instruction": "List top 3 indie songs", "app_descriptions": {}},
        {"task_id": "aaaaaaa_2", "instruction": "List top 4 rock songs", "app_descriptions": {}},
        {"task_id": "ccccccc_1", "instruction": "List top 3 indie songs", "app_descriptions": {}},
        {"task_id": "ccccccc_2", "instruction": "List top 4 rock songs", "app_descriptions": {}},
        {"task_id": "bbbbbbb_1", "instruction": "Create a note for tomorrow", "app_descriptions": {}},
        {"task_id": "ddddddd_1", "instruction": "Send a different note tomorrow", "app_descriptions": {}},
    ]}), encoding="utf-8")
    monkeypatch.setenv("REASONINGBANK_PUBLIC_DEV_DESCRIPTORS", str(inventory))
    monkeypatch.setenv("REASONINGBANK_PROTOCOL_EXCLUDED_TASK_IDS_JSON", '["aaaaaaa_1", "aaaaaaa_2", "bbbbbbb_1"]')
    monkeypatch.setattr(runner, "_hard_exposed_task_ids", lambda: (set(), {}))
    monkeypatch.setattr(runner, "_capture_python_runtime_identity", _python_runtime)
    run = tmp_path / "run"; runner.prepare(run)
    allocation = json.loads((run / "template.json").read_text(encoding="utf-8"))["allocation"]
    assert allocation["protocol_exclusion_count"] == 3
    assert set(allocation["selected"][key]["task_id"] for key in ("a", "b", "negative")).isdisjoint(
        {"aaaaaaa_1", "aaaaaaa_2", "bbbbbbb_1"})


def test_configured_external_scored_artifact_establishes_hard_task_exposure(monkeypatch, tmp_path):
    runner = _runner()
    artifact = tmp_path / "prior-run" / "artifacts" / "zzzzzzz_1" / "no_memory" / "trial-1.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(json.dumps({"task_id": "zzzzzzz_1", "arm": "no_memory", "trial_id": 1,
                                    "official_score": 1.0, "history": []}), encoding="utf-8")
    monkeypatch.setenv("REASONINGBANK_CUSTODY_ROOTS_JSON", json.dumps([str(tmp_path)]))
    exposed, trace = runner._hard_exposed_task_ids()
    assert exposed == {"zzzzzzz_1"}
    assert trace["zzzzzzz_1"] == [str(artifact)]


def test_runner_source_wires_strict_dynamic_callback_and_no_reme_boundary():
    path = Path(__file__).parents[2] / "scripts" / "run_reasoningbank_appworld_engineering.py"
    source = path.read_text(encoding="utf-8")
    assert "ReasoningBankDynamicRuntime" in source
    assert "post_score_update_strict" in source
    assert "SharedAzureOpenRouterEmbedder" in source
    assert "services(" not in source
    assert "memory_base_url" not in source
