"""Upstream-faithful ReasoningBank memory semantics for AppWorld.

The official release only includes WebArena and SWE-Bench runners.  This module
ports the benchmark-independent ReasoningBank operations while deliberately
leaving AppWorld execution and scoring to COPROMEM's shared native harness.

Upstream source: google-research/reasoning-bank@ed80611788292ea739f1effd31f16c53823b8a0d
License: Apache-2.0.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


UPSTREAM_COMMIT = "ed80611788292ea739f1effd31f16c53823b8a0d"
METHOD_VERSION = "reasoningbank-appworld-port-v1"
RETRIEVAL_K = 1

MEMORY_PROMPT = (
    "Below are some memory items that I accumulated from past interaction "
    "from the environment that may be helpful to solve the task. You can use "
    "it when you feel it's relevant. In each step, please first explicitly "
    "discuss if you want to use each memory item or not, and then take action."
)

SUCCESSFUL_EXTRACTION_PROMPT = """You are an expert in web navigation. You will be given a user query, the corresponding trajectory that represents **how an agent successfully accomplished the task**. 

## Guidelines
You need to extract and summarize useful insights in the format of memory items based on the agent's successful trajectory.
The goal of summarized memory items is to be helpful and generalizable for future similar tasks.

## Important notes
  - You must first think why the trajectory is successful, and then summarize the insights.
  - You can extract *at most 3* memory items from the trajectory.
  - You must not repeat similar or overlapping items.
  - Prefer concrete, actionable procedures over abstract principles. Do not embed specific product names, queries, or literal string contents from the task.

## Output Format
Your output must strictly follow the Markdown format shown below:

```
# Memory Item i
## Title <the title of the memory item>
## Description <one sentence summary describing when or when NOT to use the memory item>
## Content <1-3 sentences describing the insights learned to successfully accomplishing similar tasks in the future>
```
"""

FAILED_EXTRACTION_PROMPT = """You are an expert in web navigation. You will be given a user query, the corresponding trajectory that represents **how an agent attempted to resolve the task but failed**. 

## Guidelines
You need to extract and summarize useful insights in the format of memory items based on the agent's failed trajectory.
The goal of summarized memory items is to be helpful and generalizable for future similar tasks.

## Important notes
  - You must first reflect and think why the trajectory failed, and then summarize what lessons you have learned or strategies to prevent the failure in the future.
  - You can extract *at most 3* memory items from the trajectory.
  - You must not repeat similar or overlapping items.
  - Prefer concrete, actionable recovery procedures over abstract principles. Do not embed specific product names, queries, or literal string contents from the task.

## Output Format
Your output must strictly follow the Markdown format shown below:

```
# Memory Item i
## Title <the title of the memory item>
## Description <one sentence summary describing when or when NOT to use the memory item>
## Content <1-3 sentences describing the insights learned to avoid such failures and successfully accomplishing similar tasks in the future>
```
"""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _normalize(vector: Sequence[float]) -> tuple[float, ...]:
    values = tuple(float(x) for x in vector)
    norm = math.sqrt(sum(x * x for x in values))
    if not values or norm == 0.0:
        raise ValueError("ReasoningBank embeddings must be non-empty and non-zero")
    return tuple(x / norm for x in values)


def _stored_vector(vector: Sequence[float]) -> tuple[float, ...]:
    values = tuple(float(x) for x in vector)
    norm = math.sqrt(sum(x * x for x in values))
    if not values or norm == 0.0:
        raise ValueError("ReasoningBank embeddings must be non-empty and non-zero")
    if not math.isclose(norm, 1.0, rel_tol=1e-9, abs_tol=1e-9):
        raise ValueError("stored ReasoningBank embeddings must already be normalized")
    return values


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("ReasoningBank embedding dimensionality mismatch")
    return sum(a * b for a, b in zip(left, right))


@dataclass(frozen=True)
class Experience:
    experience_id: str
    task_id: str
    query: str
    status: str
    memory_items: tuple[str, ...]
    query_embedding: tuple[float, ...]
    source_trajectory_sha256: str
    judge_sha256: str
    extraction_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "experience_id": self.experience_id,
            "task_id": self.task_id,
            "query": self.query,
            "status": self.status,
            "memory_items": list(self.memory_items),
            "query_embedding": list(self.query_embedding),
            "source_trajectory_sha256": self.source_trajectory_sha256,
            "judge_sha256": self.judge_sha256,
            "extraction_sha256": self.extraction_sha256,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Experience":
        status = str(value["status"])
        if status not in {"success", "failure"}:
            raise ValueError("ReasoningBank status must be success or failure")
        return cls(
            experience_id=str(value["experience_id"]),
            task_id=str(value["task_id"]),
            query=str(value["query"]),
            status=status,
            memory_items=tuple(str(item) for item in value["memory_items"]),
            query_embedding=_stored_vector(value["query_embedding"]),
            source_trajectory_sha256=str(value["source_trajectory_sha256"]),
            judge_sha256=str(value["judge_sha256"]),
            extraction_sha256=str(value["extraction_sha256"]),
        )


@dataclass(frozen=True)
class Retrieval:
    guidance: str
    provenance: dict[str, Any]


class ReasoningBank:
    """Deterministic store around the official top-1 experience retrieval."""

    def __init__(self, experiences: Iterable[Experience] = ()) -> None:
        self._experiences = list(experiences)
        ids = [item.experience_id for item in self._experiences]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate ReasoningBank experience identity")
        for item in self._experiences:
            _stored_vector(item.query_embedding)

    @property
    def experiences(self) -> tuple[Experience, ...]:
        return tuple(self._experiences)

    def state(self) -> dict[str, Any]:
        body = {
            "method_version": METHOD_VERSION,
            "upstream_commit": UPSTREAM_COMMIT,
            "retrieval_k": RETRIEVAL_K,
            "experiences": [item.as_dict() for item in self._experiences],
        }
        return {**body, "semantic_state_sha256": sha256(body)}

    @classmethod
    def restore(cls, value: Mapping[str, Any]) -> "ReasoningBank":
        if value.get("method_version") != METHOD_VERSION:
            raise ValueError("unsupported ReasoningBank state version")
        if value.get("upstream_commit") != UPSTREAM_COMMIT or value.get("retrieval_k") != RETRIEVAL_K:
            raise ValueError("ReasoningBank upstream policy mismatch")
        body = {key: value[key] for key in ("method_version", "upstream_commit", "retrieval_k", "experiences")}
        if value.get("semantic_state_sha256") != sha256(body):
            raise ValueError("ReasoningBank state hash mismatch")
        return cls(Experience.from_dict(item) for item in value["experiences"])

    def retrieve(self, query: str, query_embedding: Sequence[float]) -> Retrieval:
        before = self.state()["semantic_state_sha256"]
        normalized = _normalize(query_embedding)
        ranked = sorted(
            ((-_cosine(normalized, item.query_embedding), index, item)
             for index, item in enumerate(self._experiences)),
            key=lambda row: (row[0], row[1]),
        )
        selected = [ranked[0][2]] if ranked else []
        blocks = [block for item in selected for block in item.memory_items if block.strip()]
        guidance = "\n\n".join(blocks)
        rendered = (MEMORY_PROMPT + "\n\n" + guidance).strip() if guidance else ""
        provenance = {
            "method_version": METHOD_VERSION,
            "upstream_commit": UPSTREAM_COMMIT,
            "query_sha256": sha256(query),
            "query_embedding_sha256": sha256(list(normalized)),
            "pre_state_sha256": before,
            "retrieval_k": RETRIEVAL_K,
            "selected_experience_ids": [item.experience_id for item in selected],
            "selected_experience_sha256s": [sha256(item.as_dict()) for item in selected],
            "guidance_sha256": sha256(guidance),
            "rendered_prompt_memory_sha256": sha256(rendered),
            "retrieval_empty": not bool(selected),
        }
        provenance["provenance_sha256"] = sha256(provenance)
        if self.state()["semantic_state_sha256"] != before:
            raise RuntimeError("ReasoningBank retrieval mutated semantic state")
        return Retrieval(guidance=guidance, provenance=provenance)

    def reproduce(self, query: str, query_embedding: Sequence[float], provenance: Mapping[str, Any]) -> str:
        current = self.retrieve(query, query_embedding)
        if current.provenance != dict(provenance):
            raise ValueError("ReasoningBank retrieval provenance does not reproduce")
        return current.guidance

    def commit(self, experience: Experience) -> str:
        if any(item.experience_id == experience.experience_id for item in self._experiences):
            existing = next(item for item in self._experiences if item.experience_id == experience.experience_id)
            if existing != experience:
                raise ValueError("conflicting ReasoningBank experience identity")
            return self.state()["semantic_state_sha256"]
        self._experiences.append(experience)
        return self.state()["semantic_state_sha256"]


def split_memory_items(text: str) -> tuple[str, ...]:
    """Mirror the official release's paragraph-level storage contract."""
    blocks = tuple(part.strip() for part in str(text).split("\n\n") if part.strip())
    if not blocks:
        raise ValueError("ReasoningBank extractor returned no memory item")
    if sum(block.startswith("# Memory Item") for block in blocks) > 3:
        raise ValueError("ReasoningBank extractor exceeded the three-item limit")
    return blocks


def build_experience(*, task_id: str, query: str, trajectory: Any, status: str,
                     judge_record: Mapping[str, Any], extraction_text: str,
                     query_embedding: Sequence[float]) -> Experience:
    """Build a content-addressed experience after external judge/extractor calls."""
    if status not in {"success", "failure"}:
        raise ValueError("ReasoningBank proxy label must be success or failure")
    trajectory_hash = sha256(trajectory)
    judge_hash = sha256(dict(judge_record))
    extraction_hash = sha256(extraction_text)
    identity = sha256({"task_id": task_id, "query": query, "trajectory": trajectory_hash,
                       "judge": judge_hash, "extraction": extraction_hash})
    return Experience(
        experience_id=f"rb_{identity[:16]}", task_id=str(task_id), query=str(query), status=status,
        memory_items=split_memory_items(extraction_text), query_embedding=_normalize(query_embedding),
        source_trajectory_sha256=trajectory_hash, judge_sha256=judge_hash,
        extraction_sha256=extraction_hash,
    )


def write_state(path: Path, bank: ReasoningBank) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(bank.state(), handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
        handle.flush()
        import os
        os.fsync(handle.fileno())
    temporary.replace(path)


def load_state(path: Path) -> ReasoningBank:
    return ReasoningBank.restore(json.loads(path.read_text(encoding="utf-8")))
