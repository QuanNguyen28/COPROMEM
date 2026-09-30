"""Zero-provider public descriptor screening for v6.2.1 engineering custody."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from .task_conditioned_retrieval_v621 import derive_task_query, retrieve, validate_task_query


SCREENING_VERSION = "v6.2.1-public-descriptor-screening-v1"


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def screen_public_descriptor(*, task_id: str, instruction: str,
                             app_descriptions: Mapping[str, Any],
                             tool_metadata: Mapping[str, Any],
                             registry: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    """Classify a supplied agent-visible descriptor without executing a task.

    The caller owns the custody boundary.  This function neither imports
    AppWorld nor receives an executor, scorer, model, provider, or lifecycle
    object.  It emits hashes and public structural labels, never instruction
    text or concrete values.
    """
    if not isinstance(task_id, str) or not task_id:
        raise ValueError("descriptor screening requires task ID")
    if not isinstance(instruction, str) or not instruction:
        raise ValueError("descriptor screening requires public instruction")
    query = derive_task_query(instruction, "appworld", tool_metadata, registry)
    validate_task_query(query, instruction=instruction, public_tool_metadata=tool_metadata,
                        callable_registry=registry)
    guidance, provenance = retrieve(state, query, registry)
    candidates = []
    for item in provenance["candidate_scores"]:
        candidates.append({key: item.get(key) for key in (
            "schema_id", "compatible", "rejection_reason", "rejection_reasons",
            "terminal_effect", "terminal_effect_supported", "positive_success_count",
            "negative_failure_count", "semantic_relevance_passed",
            "ordered_unique_operations", "schema_operation_apps",
        )})
    compatible_ids = list(provenance["selected_schema_ids"])
    return {
        "version": SCREENING_VERSION,
        "task_id": task_id,
        "instruction_sha256": hashlib.sha256(instruction.encode("utf-8")).hexdigest(),
        "instruction_feature_sha256": query["query_sha256"],
        "public_apps": sorted(map(str, app_descriptions)),
        "canonical_public_operation_candidates": query["canonical_query_operations"],
        "terminal_effect_class": (query["canonical_query_operations"][-1]
                                  if query["canonical_query_operations"] else None),
        "descriptor_sha256": digest({"apps": sorted(map(str, app_descriptions)),
                                       "query": query["canonical_query_operations"]}),
        "compatibility_class": "compatible" if compatible_ids else "incompatible",
        "compatible_schema_ids": compatible_ids,
        "candidate_features": candidates,
        "registry_sha256": registry["registry_sha256"],
        "screening_sha256": "",
        "provider_calls": 0,
    }

