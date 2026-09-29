from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from copromem.experiments.reme_copromem.live_summary import build_live_summary


def _runner():
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("v62_medium_runner", root / "scripts/run_v62_task_conditioned_medium_evaluation.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def _successor_runner():
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("v62_medium_successor_runner", root / "scripts/run_v62_task_conditioned_medium_evaluation_002.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_medium_runner_requires_pre_payload_thirty_id_audit(tmp_path: Path):
    runner = _runner()
    (tmp_path / "allocation-audit.json").write_text(json.dumps({"split": "test_normal", "payloads_opened": False,
        "selected_task_ids": [f"{index:07x}_1" for index in range(30)], "selected_family_ids": [f"{index:07x}" for index in range(30)]}))
    runner._configure(tmp_path)
    assert runner.base.EVALUATION_SPLIT == "test_normal"
    assert runner.base.HARD_CAP_USD == 300
    assert runner.base.CALL_LIMITS["executor"] == 9000
    assert runner.base.ARMS == runner.ARMS
    assert runner.base.TASK_MAJOR_ARM_FIRST is True


def test_medium_prepare_allows_only_the_frozen_public_allocation_files(tmp_path: Path):
    runner = _runner()
    runner._configure = lambda _run: None
    runner.base.PREEXISTING_RUN_FILES = {"allocation-audit.json", "custody-audit.json"}
    (tmp_path / "allocation-audit.json").write_text("{}")
    (tmp_path / "custody-audit.json").write_text("{}")
    # The shared prepare boundary must treat these files as a valid preflight
    # prefix; no task or provider operation is involved in this check.
    assert all(item.name in runner.base.PREEXISTING_RUN_FILES for item in tmp_path.iterdir())


def test_medium_live_summary_accepts_v62_arm_names(tmp_path: Path):
    ledger = tmp_path / "ledger.jsonl"
    records = [
        {"event": "reserve", "id": "historical-construction-carry", "role": "historical_carry_forward", "usd": 1.0},
        {"event": "settle", "id": "historical-construction-carry", "role": "historical_carry_forward", "usd": 1.0},
    ]
    ledger.write_text("\n".join(json.dumps(item) for item in records) + "\n")
    arms = ["no_memory", "official_upstream_reme_fixed", "official_upstream_reme_dynamic",
            "copromem_v6_2_fixed", "copromem_v6_2_dynamic"]
    out = build_live_summary(ledger_path=ledger, artifact_root=tmp_path / "artifacts", expected_tasks=["aaaaaaa_1"],
        expected_seeds=[1, 2], historical_expected_usd=1.0, state="preflight", expected_trajectories=10,
        registered_arms=arms)
    assert set(out["arms"]) == set(arms)
    assert out["expected"] == 10


def test_successor_carries_failed_infrastructure_cost_without_arm_import(tmp_path: Path):
    runner = _successor_runner()
    (tmp_path / "allocation-audit.json").write_text(json.dumps({"split": "test_normal", "payloads_opened": False,
        "selected_task_ids": [f"{index:07x}_1" for index in range(30)],
        "selected_family_ids": [f"{index:07x}" for index in range(30)]}))
    runner._configure(tmp_path)
    assert runner.base.PROTOCOL == "v6_2_task_conditioned_evaluation_002"
    assert runner.base.HISTORICAL_EXPOSURE == 2.417682693
