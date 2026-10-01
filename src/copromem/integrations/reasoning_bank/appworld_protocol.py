"""Protocol metadata and fail-closed validation for the AppWorld port."""
from __future__ import annotations

from typing import Any, Mapping

from .appworld import METHOD_VERSION, RETRIEVAL_K, UPSTREAM_COMMIT


PROFILE = "appworld-shared-harness-comparison-v1"
CONTROLLED_PORT = "ReasoningBank-AppWorld shared-backbone/shared-embedding controlled port"


def protocol_record() -> dict[str, Any]:
    return {
        "profile": PROFILE,
        "method": METHOD_VERSION,
        "upstream_repository": "https://github.com/google-research/reasoning-bank",
        "upstream_commit": UPSTREAM_COMMIT,
        "upstream_license": "Apache-2.0",
        "benchmark": "AppWorld",
        "retrieval": {"k": RETRIEVAL_K, "similarity": "cosine", "key": "task_query"},
        "embedding": {"model": "openai/text-embedding-3-small", "provider": "azure",
                      "transport": "OpenRouter", "dimensions": 1024,
                      "encoding_format": "float", "provider_fallback": False,
                      "normalization": "unit_l2_before_cosine",
                      "transport_identity": "copromem.integrations.reme.transport.LockedEmbeddings"},
        "memory_schema": ["title", "description", "content"],
        "memory_sources": ["self_judged_success", "self_judged_failure"],
        "consolidation": "append_only_no_pruning",
        "agent_temperature": 0.7,
        "judge_temperature": 0.0,
        "extractor_temperature": 1.0,
        "appworld_official_scorer_used_for_analysis_only": True,
        "appworld_official_scorer_used_for_memory_label": False,
        "claim": "ReasoningBank-AppWorld shared-backbone/shared-embedding controlled port; not an official paper reproduction",
    }


def validate_protocol(value: Mapping[str, Any]) -> None:
    expected = protocol_record()
    if dict(value) != expected:
        raise ValueError("ReasoningBank AppWorld protocol drift")
