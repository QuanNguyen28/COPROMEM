"""Provider-agnostic ReasoningBank online lifecycle.

Network/model calls are injected as callbacks so the production runner can
ledger and pin them.  This module never reads AppWorld's official score; the
paper's self-judge signal remains a separate model output.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from .appworld import (
    FAILED_EXTRACTION_PROMPT,
    SUCCESSFUL_EXTRACTION_PROMPT,
    ReasoningBank,
    Retrieval,
    build_experience,
    render_retrieval_guidance,
    sha256,
)


Embedder = Callable[[str, str], Sequence[float]]
Judge = Callable[[str, Any, float], tuple[str, Mapping[str, Any]]]
Extractor = Callable[[str, str, Any, float], tuple[str, Mapping[str, Any]]]


@dataclass(frozen=True)
class UpdateResult:
    pre_state_sha256: str
    post_state_sha256: str
    experience_id: str
    status: str
    judge_record_sha256: str
    extractor_record_sha256: str


class ReasoningBankLifecycle:
    def __init__(self, *, bank: ReasoningBank, embedder: Embedder,
                 judge: Judge, extractor: Extractor) -> None:
        self.bank = bank
        self.embedder = embedder
        self.judge = judge
        self.extractor = extractor
        self.last_retrieval: Retrieval | None = None
        self.last_query_embedding: tuple[float, ...] | None = None

    def retrieve_for_instruction(self, instruction: str, _benchmark: str,
                                 _metadata: Mapping[str, Any]) -> str:
        vector = self.embedder(instruction, "RETRIEVAL_QUERY")
        result = self.bank.retrieve(instruction, vector)
        self.last_retrieval = result
        self.last_query_embedding = tuple(float(item) for item in vector)
        # The shared AppWorld executor owns the outer memory slot. Keep the
        # official instruction and selected memory in one authoritative render.
        return render_retrieval_guidance(result.guidance)

    def update(self, *, task_id: str, query: str, trajectory: Any) -> UpdateResult:
        """Self-judge and append one new experience after a trajectory.

        The AppWorld official score is intentionally absent from this API.
        """
        pre = self.bank.state()["semantic_state_sha256"]
        status, judge_record = self.judge(query, trajectory, 0.0)
        if status not in {"success", "failure"}:
            raise ValueError("ReasoningBank self-judge must return success or failure")
        system_prompt = SUCCESSFUL_EXTRACTION_PROMPT if status == "success" else FAILED_EXTRACTION_PROMPT
        extraction, extractor_record = self.extractor(system_prompt, query, trajectory, 1.0)
        vector = self.embedder(query, "RETRIEVAL_DOCUMENT")
        item = build_experience(task_id=task_id, query=query, trajectory=trajectory, status=status,
                                judge_record=judge_record, extraction_text=extraction,
                                query_embedding=vector)
        post = self.bank.commit(item)
        return UpdateResult(pre, post, item.experience_id, status,
                            sha256(dict(judge_record)), sha256(dict(extractor_record)))
