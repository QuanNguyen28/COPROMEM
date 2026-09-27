from pathlib import Path

import pytest

from copromem.appworld_acquisition_gate import AcquisitionIncomplete, AcquisitionJournal, AcquisitionRef
from copromem.checkpoints import RunStore


def _journal(tmp_path: Path) -> AcquisitionJournal:
    journal = AcquisitionJournal(RunStore(tmp_path), AcquisitionRef("fixture", 0, 0))
    journal.start(task_manifest_sha256="task", base_prompt_sha256="prompt", tool_schema_sha256="tools")
    return journal


def test_interrupted_paid_action_cannot_admit_evaluation(tmp_path):
    # Regression for 50e1ac9_1: a reservation/paid request exists but the
    # controller ends before a native action and official scorer artifact.
    journal = _journal(tmp_path)
    with pytest.raises(AcquisitionIncomplete, match="complete trace"):
        journal.approve_evaluation()


def test_empty_trace_is_hashed_but_cannot_admit_evaluation(tmp_path):
    journal = _journal(tmp_path)
    assert journal.finish(official_score={"success": False})
    with pytest.raises(AcquisitionIncomplete, match="complete trace"):
        journal.approve_evaluation()


def test_complete_trace_score_and_distinct_method_memories_admit(tmp_path):
    journal = _journal(tmp_path)
    journal.action(0, code="apis.fixture.do()", native_output={"ok": True, "output": "private"}, completed=True)
    trace = journal.finish(official_score={"success": True, "pass_count": 2, "num_tests": 2})
    journal.admit_memory(method="reme_fixed_faithful_adaptation", provenance="reme-adapter-v1", memory_text="Retrieve verified fixture state.")
    journal.admit_memory(method="reme_dynamic_faithful_adaptation", provenance="reme-adapter-v1-dynamic", memory_text="Retrieve and update verified fixture state.")
    journal.admit_memory(method="copromem_v2", provenance="copromem-v2", memory_text="Use observed fixture procedure and verify.")
    admitted = journal.approve_evaluation()
    assert admitted["raw_trajectory_sha256"] == trace
    assert len({admitted["reme_fixed_faithful_adaptation"], admitted["copromem_v2"]}) == 2


def test_generic_placeholder_is_rejected(tmp_path):
    journal = _journal(tmp_path)
    journal.action(0, code="apis.fixture.do()", native_output={"ok": True}, completed=True)
    journal.finish(official_score={"success": False})
    with pytest.raises(AcquisitionIncomplete, match="generic"):
        journal.admit_memory(method="copromem_v2", provenance="copromem-v2", memory_text="Shared acquisition failures retained.")


def test_restart_recovers_persisted_action_plan_without_a_model_replay(tmp_path):
    journal = _journal(tmp_path)
    journal.plan_action(0, code="apis.fixture.do()")
    restarted = AcquisitionJournal(RunStore(tmp_path), AcquisitionRef("fixture", 0, 0))
    assert restarted.pending_plans() == [{"task_id": "fixture", "index": 0, "code": "apis.fixture.do()"}]
    restarted.action(0, code="apis.fixture.do()", native_output={"ok": True}, completed=False)
    assert restarted.pending_plans() == []
