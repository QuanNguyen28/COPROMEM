import json
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal

import pytest

from copromem.checkpoints import (
    GenerationService,
    IntegrityError,
    PlannerCheckpoint,
    RunStore,
    canonical,
    matched_seed,
)
from copromem.paired_gsm8k import (
    ARMS,
    GSM8KAdapter,
    PairedConfig,
    paired_summary,
    resume_arm,
    run_paired_experiment,
)
from copromem.real_gsm8k_experiment import CallResult, Example, Usage


class StatefulProvider:
    """Deliberately changes each solver answer, even for an identical prompt."""

    model = "mock/stateful-v1"
    seed = 0

    def __init__(self):
        self.calls = 0
        self.prompts = []

    def chat(self, system, user, max_tokens, *, seed=None):
        self.calls += 1
        self.prompts.append((system, user, max_tokens, seed))
        usage = Usage(10, 10, 20, usd=0.001, latency_seconds=0.01)
        if "solving agent" in system:
            text = f"FINAL_ANSWER: {self.calls}"
        elif (
            "Repair the artifact" in user
            or "regenerate the artifact" in user
            or "build" in user
        ):
            text = '{"operations":["add"],"answer_unit":"items","check":"inverse"}'
        else:
            text = '{"operations":["add"],"answer_unit":"items","check":""}'
        return CallResult(text, usage, self.model)


def fixtures():
    return [Example("build-1", "build item count", Decimal(2))], [
        Example("dev-1", "evaluate item count", Decimal(7)),
        Example("dev-2", "evaluate another item count", Decimal(9)),
    ]


def prior():
    return {
        "evidence": {
            "build_failures": 1,
            "failures_with_observable_violation": 1,
            "successful_valid_handoffs": 1,
        }
    }


def test_frozen_checkpoint_returns_nested_deep_copies_and_roundtrips(tmp_path):
    checkpoint = PlannerCheckpoint(
        "a",
        "question",
        "dev",
        "math",
        0,
        canonical({"ops": ["original"]}),
        "generation",
    )
    external = checkpoint.artifact()
    external["ops"].append("poison")
    assert checkpoint.artifact() == {"ops": ["original"]}
    with pytest.raises(FrozenInstanceError):
        checkpoint.artifact_json = "{}"
    store = RunStore(tmp_path)
    checkpoint.save(store)
    assert PlannerCheckpoint.load(store, checkpoint.checkpoint_id) == checkpoint
    path = tmp_path / "checkpoints" / f"{checkpoint.checkpoint_id}.json"
    payload = json.loads(path.read_text())
    payload["question"] = "tampered"
    path.write_text(json.dumps(payload))
    with pytest.raises(IntegrityError):
        PlannerCheckpoint.load(store, checkpoint.checkpoint_id)


def test_write_once_store_rejects_overwrite(tmp_path):
    store = RunStore(tmp_path)
    store.write("protocol", "manifest", {"fixed": 1})
    with pytest.raises(IntegrityError):
        store.write("protocol", "manifest", {"fixed": 2})


@pytest.mark.parametrize(
    "key", ["../outside", "C:\\private", "name:stream", "..", "trailing."]
)
def test_store_rejects_unsafe_components_on_reads_and_writes(tmp_path, key):
    store = RunStore(tmp_path)
    with pytest.raises(ValueError):
        store.read("calls", key)
    with pytest.raises(ValueError):
        store.write("calls", key, {})


def test_shared_checkpoints_static_control_and_accounting(tmp_path):
    client = StatefulProvider()
    build, dev = fixtures()
    report = run_paired_experiment(
        client, build, dev, prior_memory=prior(), store_path=tmp_path
    )
    assert set(report["evaluation"]) == set(ARMS)
    for index in range(len(dev)):
        rows = [report["evaluation"][arm]["tasks"][index] for arm in ARMS]
        assert len({row["checkpoint_id"] for row in rows}) == 1
        assert len({row["initial_artifact_sha256"] for row in rows}) == 1
        assert len({row["solver_seed"] for row in rows}) == 1
        assert all(row["calls"] <= 2 for row in rows)
        control = report["evaluation"]["static_verifier"]["tasks"][index]
        treatment = report["evaluation"]["copromem"]["tasks"][index]
        assert control["call_ids"] == treatment["call_ids"]
        assert control["predicted"] == treatment["predicted"]
    assert report["paired"]["copromem_vs_static_verifier"]["net_gain"] == 0
    assert report["experiment_totals"]["measured_agent_calls"] == client.calls
    assert report["experiment_totals"]["measured_cost_usd"] == pytest.approx(
        client.calls * 0.001
    )
    assert report["protocol"]["config"]["seed"] == 0
    assert all(prompt[3] is not None for prompt in client.prompts)


def test_no_intervention_shares_solver_draw_even_with_nondeterministic_provider():
    client = StatefulProvider()
    build, dev = fixtures()
    report = run_paired_experiment(client, build, dev)
    assert report["memory_construction"]["copromem_contract"]["admitted"] is False
    assert report["paired"]["copromem_vs_no_memory"]["net_gain"] == 0
    assert all(
        row["same_solver_request"]
        for row in report["paired"]["copromem_vs_no_memory"]["details"]
    )


def test_resume_uses_saved_requests_and_no_new_provider_calls(tmp_path):
    client = StatefulProvider()
    build, dev = fixtures()
    first = run_paired_experiment(
        client, build, dev, prior_memory=prior(), store_path=tmp_path
    )
    new_client = StatefulProvider()
    second = run_paired_experiment(
        new_client, build, dev, prior_memory=prior(), store_path=tmp_path
    )
    assert new_client.calls == 0
    assert first["evaluation"] == second["evaluation"]
    assert second["experiment_totals"]["physical_calls_this_invocation"] == 0
    assert (
        first["experiment_totals"]["unique_usd_in_protocol"]
        == second["experiment_totals"]["unique_usd_in_protocol"]
    )


def test_reordered_arm_declaration_cannot_change_outcomes():
    build, dev = fixtures()
    first = run_paired_experiment(StatefulProvider(), build, dev, arms=ARMS)
    second = run_paired_experiment(
        StatefulProvider(), build, dev, arms=tuple(reversed(ARMS))
    )
    assert first["evaluation"] == second["evaluation"]


@pytest.mark.parametrize("kind", ["id", "question", "duplicate"])
def test_leakage_rejected_before_any_generation(kind):
    client = StatefulProvider()
    build, dev = fixtures()
    if kind == "id":
        dev[0] = replace(dev[0], example_id=build[0].example_id)
    elif kind == "question":
        dev[0] = replace(dev[0], question="  BUILD   item count  ")
    else:
        dev.append(dev[0])
    with pytest.raises(ValueError):
        run_paired_experiment(client, build, dev)
    assert client.calls == 0


def test_stage_seeds_are_stable_arm_independent_and_replicate_specific():
    assert matched_seed(17, "a", "solver", 0) == matched_seed(17, "a", "solver", 0)
    assert (
        len(
            {
                matched_seed(17, "a", stage, replicate)
                for stage in ("planner", "solver", "recovery")
                for replicate in range(3)
            }
        )
        == 9
    )


def test_arm_failure_is_logged_and_next_arm_can_continue(tmp_path):
    class FailsOnce(StatefulProvider):
        def chat(self, system, user, max_tokens, *, seed=None):
            if "Repair the artifact" in user and not getattr(self, "did_fail", False):
                self.did_fail = True
                raise OSError("SECRET must not appear in records")
            return super().chat(system, user, max_tokens, seed=seed)

    client = FailsOnce()
    store = RunStore(tmp_path)
    adapter = GSM8KAdapter(GenerationService(client, store, "test"), PairedConfig())
    example = fixtures()[1][0]
    checkpoint, _ = adapter.checkpoint(example, "dev", 0)
    failed = resume_arm(
        adapter, checkpoint, example, "static_verifier", None, {"admitted": True}
    )
    other = resume_arm(
        adapter, checkpoint, example, "copromem", None, {"admitted": True}
    )
    assert failed["failure"] and other["failure"] is None
    assert failed["checkpoint_id"] == other["checkpoint_id"]
    failure_files = list((tmp_path / "failures").glob("*.json"))
    assert len(failure_files) == 1
    assert "SECRET" not in failure_files[0].read_text()


def test_all_arms_use_same_scorer_and_gold_never_enters_prompts(tmp_path):
    build, dev = fixtures()
    dev = [replace(x, gold=Decimal("987654321.75")) for x in dev]
    client = StatefulProvider()
    report = run_paired_experiment(client, build, dev, store_path=tmp_path)
    assert not any("987654321.75" in prompt[1] for prompt in client.prompts)
    for arm in ARMS:
        assert report["evaluation"][arm]["metrics"]["task_success"]["correct"] == 0
    for path in (tmp_path / "checkpoints").glob("*.json"):
        assert "gold" not in json.loads(path.read_text())


def test_paired_summary_rejects_misalignment_and_clusters_replicates():
    build, dev = fixtures()
    config = PairedConfig(replicates=2)
    report = run_paired_experiment(StatefulProvider(), build, dev, config=config)
    old = report["evaluation"]["no_memory"]["tasks"]
    new = report["evaluation"]["copromem"]["tasks"]
    assert paired_summary(old, new, config)["unique_tasks"] == 2
    with pytest.raises(ValueError):
        paired_summary(old, new[:-1], config)
    corrupted = [dict(row) for row in new]
    corrupted[0]["checkpoint_id"] = "wrong"
    with pytest.raises(ValueError):
        paired_summary(old, corrupted, config)
