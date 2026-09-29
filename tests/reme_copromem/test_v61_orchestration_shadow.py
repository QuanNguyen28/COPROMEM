"""Zero-provider shadow of the maintained five-arm v6.1 orchestration.

The test calls the production ``run`` function.  Only the external executor,
service HTTP boundary, and scorer are replaced with deterministic local
fixtures; ledgers, artifact contract, summaries, checkpoint manager, status
finalization, ordering, and the CoProMem task boundary stay in the production
control flow.
"""
from __future__ import annotations

import contextlib
import importlib.util
import json
import pathlib
import sys
from types import SimpleNamespace

import pytest

from copromem.experiments.reme_copromem.evidence_contract import bind
from copromem.experiments.reme_copromem.runner import append, write_json
from copromem.integrations.reme.bank import semantic_bank_hash


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run_v61_exploratory_evaluation.py"


def _module():
    spec = importlib.util.spec_from_file_location("v61_shadow_runner", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _rows(path: pathlib.Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _shadow(monkeypatch, tmp_path: pathlib.Path, *, interrupt: str | None = None,
            interrupt_on_call_number: int | None = None):
    mod = _module(); run = tmp_path / "shadow"; run.mkdir()
    shared = tmp_path / "construction" / "reme" / "shared-bank.jsonl"
    initial_rows = [{"memory_id": "m0", "memory": "initial", "vector": [0.1, 0.2]}]
    _rows(shared, initial_rows)
    banks = {"fake://reme-fixed": list(initial_rows), "fake://reme-dynamic": list(initial_rows),
             "fake://reme-dynamic-verifier": []}
    copro = tmp_path / "copro" / "fixed-bank.json"; copro.parent.mkdir(parents=True)
    copro.write_text(json.dumps({"contrastive_v6_schemas": {"s": {"terminal_effect": "x"}}}), encoding="utf-8")
    manifest = {
        "arms": list(mod.ARMS), "evaluation": {"task_ids": ["shadow-a", "shadow-b"], "seeds": [11, 12], "expected_trajectories": 20},
        "banks": {"reme_shared_sha256": semantic_bank_hash(shared),
                  "copromem_sha256": mod.digest({"contrastive_v6_schemas": {"s": {"terminal_effect": "x"}}})},
        "budget": {"call_limits": {"executor": 100, "reme_lifecycle": 20, "reme_embedding": 20, "copromem_decomposition": 0}},
        "storage_policy": {"launch_floor_gib": 5, "warning_gib": 4, "mandatory_stop_gib": 3},
    }
    write_json(run / "manifest.json", manifest); (run / "manifest.sha256").write_text(mod.file_sha(run / "manifest.json") + "\n")
    monkeypatch.setattr(mod, "load", lambda _run: manifest); monkeypatch.setattr(mod, "key", lambda: "local")
    monkeypatch.setattr(mod, "COPRO", copro.parent); monkeypatch.setattr(mod, "CONSTRUCTION", tmp_path / "construction")
    monkeypatch.setattr(mod, "guard", lambda *_args: None)
    calls: list[str] = []
    def post(url, endpoint, value):
        key = str(url)
        if endpoint == "load_memory":
            banks[key] = [json.loads(line) for line in pathlib.Path(value["load_file_path"]).read_text().splitlines()]
        elif endpoint == "dump_memory": _rows(pathlib.Path(value["dump_file_path"]), banks[key])
        return {"success": True}
    monkeypatch.setattr(mod, "official_post", post)
    @contextlib.contextmanager
    def fake_services(*_args, **_kwargs):
        yield {name: SimpleNamespace(base_url=f"fake://{name}") for name in ("reme-fixed", "reme-dynamic", "reme-dynamic-verifier")}
    monkeypatch.setattr(mod, "services", fake_services)
    import copromem.integrations.reme.lifecycle as lifecycle
    def local_dynamic_update(agent, _score, _event):
        banks[agent.base_url].append({"memory_id": f"m{len(banks[agent.base_url])}", "memory": "updated", "vector": [0.3, 0.4]})
    monkeypatch.setattr(lifecycle, "dynamic_post_trial_update", local_dynamic_update)
    def fake_retrieval(**_kwargs): return "shadow guidance", {"shadow": True}
    monkeypatch.setattr(mod, "retrieval_record", fake_retrieval)
    def fake_batch(**kwargs):
        assert len(kwargs["artifacts"]) == 2
        post_state = {**kwargs["pre_state"], "shadow_updates": len(kwargs["artifacts"])}
        plan = {"plan_sha256": "shadow-plan"}
        return post_state, {"state": "committed", "winner_schema_id": "shadow-schema"}, {
            "shadow": True, "plan": plan, "validation": {"passed": True},
            "semantic_graph_audits": [{"semantic_projection_sha256": "shadow-1"}, {"semantic_projection_sha256": "shadow-2"},
        ]}
    monkeypatch.setattr(mod, "semantic_task_batch_update", fake_batch)
    def fake_execute(**kwargs):
        arm, task, trial, seed = kwargs["arm"], kwargs["task_id"], kwargs["trial_id"], kwargs["seed"]
        if kwargs.get("memory_for_instruction") is not None:
            kwargs["memory_for_instruction"]("shadow public instruction", "appworld", {"app_descriptions": {}})
        if interrupt_on_call_number is not None and len(calls) + 1 == interrupt_on_call_number:
            raise KeyboardInterrupt()
        call_id = f"shadow-{arm}-{task}-{trial}"
        if interrupt == "before_reservation": raise KeyboardInterrupt()
        kwargs["ledger"].reserve(call_id, .01, {"role": f"executor:{arm}:{task}:trial={trial}:seed={seed}"})
        if interrupt == "after_reservation": raise KeyboardInterrupt()
        kwargs["ledger"].settle(call_id, .005, {"role": f"executor:{arm}:{task}:trial={trial}:seed={seed}"})
        journal = run / "journals" / f"{arm}-{task}-{trial}.jsonl"; journal.parent.mkdir(exist_ok=True)
        if interrupt == "after_journal_creation": raise KeyboardInterrupt()
        journal.write_text('{"event":"response_attested"}\n', encoding="utf-8")
        trajectory_id = f"evaluation:{arm}:{task}:trial={trial}:seed={seed}"
        scorer = run / "scorer" / f"{arm}-{task}-{trial}.jsonl"
        _rows(scorer, [{"event": "official_score", "trajectory_id": trajectory_id, "task_id": task,
                        "pass_count": 1, "fail_count": 0}])
        history = [{"role": "assistant", "content": "local"}]
        binding = bind(journal=journal, run_root=run, registry_sha256=json.loads(mod.REG.read_text())["registry_sha256"],
                       scorer_journal=scorer, trajectory_id=trajectory_id, task_id=task, after_score=1.0,
                       history_sha256=mod.digest(history))
        result = {"trajectory_id": trajectory_id, "arm": arm, "task_id": task, "trial_id": trial, "seed": seed,
                  "after_score": 1.0, "before_score": 0.0, "actions": 1, "history": history,
                  "history_sha256": mod.digest(history), **binding}
        write_json(kwargs["artifact_path"], result); append(kwargs["progress"], {"event": "trajectory_scored", "trajectory_id": result["trajectory_id"]})
        if interrupt == "after_scored_artifact": raise KeyboardInterrupt()
        if kwargs.get("post_score_update") is not None:
            kwargs["post_score_update"](SimpleNamespace(base_url="fake://reme-dynamic"), result, None)
        calls.append(result["trajectory_id"])
        return result
    monkeypatch.setattr(mod, "execute_trajectory", fake_execute)
    return mod, run, calls


def test_full_shadow_uses_production_orchestration_and_refreshes_every_artifact(monkeypatch, tmp_path):
    mod, run, calls = _shadow(monkeypatch, tmp_path)
    mod.run(run)
    summary = json.loads((run / "live-summary.json").read_text())
    assert len(calls) == 20 and summary["completed"] == summary["expected"] == 20
    assert all(summary["arms"][arm]["Completed"] == 4 for arm in mod.ARMS)
    assert all(summary["arms"][arm]["ExecutorCalls"] == 4 for arm in mod.ARMS)
    assert json.loads((run / "runner-status.json").read_text())["state"] == "completed"
    assert not (run / "runner.lock").exists()


@pytest.mark.parametrize("point", ["before_reservation", "after_reservation", "after_journal_creation", "after_scored_artifact"])
def test_shadow_interruptions_are_terminal_and_never_mark_dead_runner_running(monkeypatch, tmp_path, point):
    mod, run, _calls = _shadow(monkeypatch, tmp_path, interrupt=point)
    with pytest.raises(KeyboardInterrupt): mod.run(run)
    assert json.loads((run / "runner-status.json").read_text())["state"] == "failed"
    assert not (run / "runner.lock").exists()


def test_evaluation_005_sequence_has_two_durable_summaries_before_interrupt(monkeypatch, tmp_path):
    mod, run, _calls = _shadow(monkeypatch, tmp_path, interrupt_on_call_number=3)
    with pytest.raises(KeyboardInterrupt): mod.run(run)
    summary = json.loads((run / "live-summary.json").read_text())
    assert summary["completed"] == 2
    assert summary["arms"]["no_memory"]["Completed"] == 1
    assert summary["arms"]["official_upstream_reme_fixed"]["Completed"] == 1
    assert summary["arms"]["no_memory"]["ExecutorCost"] > 0
