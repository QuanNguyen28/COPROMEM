from __future__ import annotations

from copromem.integrations.reasoning_bank.appworld import ReasoningBank
from copromem.integrations.reasoning_bank.lifecycle import ReasoningBankLifecycle


def test_online_lifecycle_learns_from_success_and_retrieves_without_score():
    calls = []

    def embed(text, task_type):
        calls.append(("embed", task_type, text))
        return [1.0, 0.0]

    def judge(query, trajectory, temperature):
        calls.append(("judge", temperature, query, trajectory))
        return "success", {"label": "success", "call": "judge-1"}

    def extract(system, query, trajectory, temperature):
        calls.append(("extract", temperature, query, trajectory))
        return "# Memory Item 1\n## Title Safe deletion\n## Description Use for deletion\n## Content Verify the target before deletion.", {"call": "extract-1"}

    lifecycle = ReasoningBankLifecycle(bank=ReasoningBank(), embedder=embed,
                                       judge=judge, extractor=extract)
    update = lifecycle.update(task_id="t1", query="delete item", trajectory=["act"])
    assert update.status == "success"
    assert update.pre_state_sha256 != update.post_state_sha256
    assert all("official_score" not in str(call) for call in calls)
    guidance = lifecycle.retrieve_for_instruction("delete another item", "appworld", {})
    assert "Below are some memory items" in guidance
    assert "Verify the target" in guidance
    assert lifecycle.last_retrieval.provenance["selected_experience_ids"] == [update.experience_id]


def test_failure_uses_failure_extraction_temperature_one():
    seen = {}

    def extractor(system, query, trajectory, temperature):
        seen.update(system=system, temperature=temperature)
        return "# Memory Item 1\n## Title Avoid stale IDs\n## Description Failed navigation\n## Content Refresh observations before retrying.", {"call": "e"}

    lifecycle = ReasoningBankLifecycle(
        bank=ReasoningBank(), embedder=lambda *_: [1.0],
        judge=lambda *_: ("failure", {"label": "failure"}), extractor=extractor,
    )
    lifecycle.update(task_id="t", query="q", trajectory=[])
    assert seen["temperature"] == 1.0
    assert "attempted to resolve the task but failed" in seen["system"]
