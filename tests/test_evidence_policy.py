"""Behavioral checks for evidence admission and evaluation isolation."""

import pytest

from copromem.copromem_memory_module import COPROMEMMemoryModule, ProceduralMemoryItem
from copromem.evidence_policy import TransferObservation


def _module() -> COPROMEMMemoryModule:
    module = COPROMEMMemoryModule(api_key="")
    module.add_memory(ProceduralMemoryItem(
        memory_id="source_10", source_task_id="10",
        intent="Find the current sales metric", title="Sales lookup",
        description="", procedure="Open report and read sales metric",
        constraints={}, domain="shop", source="archived_success",
    ))
    return module


def _observation(task_id: str, *, base: bool, memory: bool) -> TransferObservation:
    return TransferObservation(
        memory_id="source_10", source_task_id="10", task_id=task_id,
        family="template_1", constraints={},
        without_memory_success=base, with_memory_success=memory,
        initial_state_digest="a" * 64,
    )


def test_memory_requires_paired_gain_and_abstains_after_harm():
    module = _module()
    query = dict(task_id="eval_1", intent="Find the current sales metric",
                 domain="shop")
    assert module.retrieve_memory("copromem_evidence", **query).selected_memory_id is None
    module.record_transfer_observation(_observation("cal_1", base=False, memory=True))
    module.record_transfer_observation(_observation("cal_2", base=True, memory=True))
    assert module.retrieve_memory("copromem_evidence", **query).selected_memory_id == "source_10"
    module.record_transfer_observation(_observation("cal_3", base=True, memory=False))
    result = module.retrieve_memory("copromem_evidence", **query)
    assert result.selected_memory_id is None
    assert "harmful" in result.selection_reason


def test_frozen_evaluation_state_cannot_learn_from_evaluation_task():
    module = _module()
    module.record_transfer_observation(_observation("cal_1", base=False, memory=True))
    module.record_transfer_observation(_observation("cal_2", base=True, memory=True))
    module.freeze_evaluation({"eval_1"})
    restored = COPROMEMMemoryModule(api_key="")
    restored.load_state(module.export_state())
    before = restored.export_state()
    result = restored.retrieve_memory(
        "copromem_evidence", "eval_1", "Find the current sales metric", "shop",
    )
    assert result.selected_memory_id == "source_10"
    assert restored.export_state() == before
    with pytest.raises(ValueError, match="frozen"):
        restored.record_transfer_observation(_observation("eval_1", base=False, memory=True))
    with pytest.raises(ValueError, match="frozen"):
        restored.record_episode("eval_1", "copromem_evidence", True, {}, result.schema)
    with pytest.raises(ValueError, match="outside"):
        restored.retrieve_memory(
            "copromem_evidence", "other", "Find the current sales metric", "shop",
        )
