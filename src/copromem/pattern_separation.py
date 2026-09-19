"""Pattern Separation Engine: Disentangling semantically similar tasks with divergent causal structures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .schema import DecompositionSchema


def token_jaccard_similarity(tokens_a: tuple[str, ...], tokens_b: tuple[str, ...]) -> float:
    """Calculate token-level Jaccard similarity between two sets of semantic cues."""
    set_a = {t.lower().strip() for t in tokens_a if t.strip()}
    set_b = {t.lower().strip() for t in tokens_b if t.strip()}
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def calculate_graph_distance(schema_a: DecompositionSchema, schema_b: DecompositionSchema) -> float:
    """Compute structural graph distance between two schemas.

    Returns a normalized value in [0.0, 1.0], where 0.0 means isomorphic roles & edges,
    and 1.0 means completely disjoint/opposite structures.
    """
    # 1. Role/Node distance
    roles_a = {n.role for n in schema_a.nodes}
    roles_b = {n.role for n in schema_b.nodes}
    union_roles = roles_a | roles_b
    role_dist = 1.0 - (len(roles_a & roles_b) / len(union_roles)) if union_roles else 0.0

    # 2. Dependency Edge distance (normalized by directed edge pairs)
    edges_a = {(e.source_node, e.target_node) for e in schema_a.edges}
    edges_b = {(e.source_node, e.target_node) for e in schema_b.edges}
    union_edges = edges_a | edges_b
    edge_dist = 1.0 - (len(edges_a & edges_b) / len(union_edges)) if union_edges else 0.0

    # 3. Precondition mismatch
    pre_a = set(schema_a.preconditions)
    pre_b = set(schema_b.preconditions)
    union_pre = pre_a | pre_b
    pre_dist = 1.0 - (len(pre_a & pre_b) / len(union_pre)) if union_pre else 0.0

    # Weighted structural distance
    return 0.3 * role_dist + 0.5 * edge_dist + 0.2 * pre_dist


@dataclass(frozen=True)
class PatternSeparationDecision:
    """Decision produced by the pattern separation engine."""

    should_separate: bool
    reason: str
    semantic_similarity: float
    causal_distance: float
    suggested_variant_id: str | None = None


class PatternSeparationEngine:
    """Detects when high surface semantic resemblance hides conflicting causal structure.

    If semantic similarity exceeds semantic_threshold, but causal/graph distance exceeds
    causal_threshold, the engine flags a negative-transfer hazard and recommends
    isolating the schemas (Pattern Separation).
    """

    def __init__(
        self,
        semantic_threshold: float = 0.40,
        causal_threshold: float = 0.35,
    ) -> None:
        self.semantic_threshold = semantic_threshold
        self.causal_threshold = causal_threshold

    def evaluate(
        self,
        task_cues: tuple[str, ...],
        task_state: dict[str, Any],
        candidate: DecompositionSchema,
        candidate_state: dict[str, Any] | None = None,
    ) -> PatternSeparationDecision:
        # Calculate semantic similarity between task cues and candidate cues
        semantic_sim = token_jaccard_similarity(task_cues, candidate.semantic_cues)

        # Calculate causal conflict based on preconditions and task invariants
        task_intent = task_state.get("intent")
        candidate_intent = (candidate_state or {}).get("intent")

        causal_conflict = 0.0
        # If task intent is explicitly divergent (e.g. preserve rows vs intentional expansion)
        if candidate_intent and task_intent and task_intent != candidate_intent:
            causal_conflict += 0.60

        # Check for counterexamples in candidate contracts
        task_id = str(task_state.get("task_id", ""))
        for contract in candidate.contracts:
            if task_id and task_id in contract.counterexamples:
                causal_conflict += 0.50
            if task_intent and any(ce == task_intent for ce in contract.counterexamples):
                causal_conflict += 0.50

        # Check preconditions in candidate
        missing_preconditions = [
            p for p in candidate.preconditions if not task_state.get(p, True)
        ]
        if missing_preconditions:
            causal_conflict += 0.40 * (len(missing_preconditions) / len(candidate.preconditions))

        causal_conflict = min(1.0, causal_conflict)

        # Check separation criterion
        if semantic_sim >= self.semantic_threshold and causal_conflict >= self.causal_threshold:
            variant_id = f"{candidate.schema_id}_variant_{task_intent or 'separated'}"
            return PatternSeparationDecision(
                should_separate=True,
                reason=(
                    f"Negative transfer risk: Semantic similarity is high ({semantic_sim:.2f} >= "
                    f"{self.semantic_threshold:.2f}), but causal conflict is high "
                    f"({causal_conflict:.2f} >= {self.causal_threshold:.2f})."
                ),
                semantic_similarity=semantic_sim,
                causal_distance=causal_conflict,
                suggested_variant_id=variant_id,
            )

        return PatternSeparationDecision(
            should_separate=False,
            reason="Compatible structure: No structural conflict detected.",
            semantic_similarity=semantic_sim,
            causal_distance=causal_conflict,
            suggested_variant_id=None,
        )
