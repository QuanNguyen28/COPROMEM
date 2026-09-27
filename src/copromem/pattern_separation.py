"""Pattern Separation Engine: Disentangling semantically similar tasks with divergent causal structures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .schema import DecompositionSchema


import re


def normalize_cues(tokens: tuple[str, ...] | list[str] | str) -> set[str]:
    """Normalize text or tokens into clean word stems without punctuation or hyphens."""
    if isinstance(tokens, str):
        text = tokens
    else:
        text = " ".join(tokens)
    words = re.findall(r"\w+", text.lower())
    stopwords = {"a", "an", "the", "me", "my", "our", "about", "tell", "why", "what", "which", "who", "is", "are", "of", "in", "for"}
    res = set()
    for w in words:
        if not w or w in stopwords:
            continue
        if w.endswith("s") and len(w) > 3 and not w.endswith("ss"):
            res.add(w[:-1])
        else:
            res.add(w)
    return res


def token_jaccard_similarity(tokens_a: tuple[str, ...] | list[str] | str, tokens_b: tuple[str, ...] | list[str] | str) -> float:
    """Calculate token-level Jaccard similarity between two sets of semantic cues."""
    set_a = normalize_cues(tokens_a)
    set_b = normalize_cues(tokens_b)
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
    divergent_constraints: dict[str, tuple[Any, Any]] = None

    def __post_init__(self) -> None:
        if self.divergent_constraints is None:
            object.__setattr__(self, "divergent_constraints", {})


class PatternSeparationEngine:
    """Detects when high surface semantic resemblance hides conflicting causal structure.

    In cognitive architecture (hippocampal DG-CA3 circuits), negative transfer occurs
    only when surface cues are deceptively similar (semantic_sim >= semantic_threshold),
    while the underlying causal invariants or state constraints diverge (causal_conflict >= causal_threshold).
    If surface similarity is low, the memories are merely orthogonal, not a negative transfer hazard.
    """

    def __init__(
        self,
        semantic_threshold: float = 0.35,
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
        task_schema: DecompositionSchema | None = None,
    ) -> PatternSeparationDecision:
        # Calculate semantic similarity between task cues and candidate cues
        semantic_sim = token_jaccard_similarity(task_cues, candidate.semantic_cues)

        # Calculate causal conflict based on preconditions, intent, and constraints
        task_intent = task_state.get("intent")
        candidate_intent = (candidate_state or {}).get("intent")
        causal_conflict = 0.0
        divergent_constraints: dict[str, tuple[Any, Any]] = {}

        task_constraints = task_state.get("constraints", {})
        candidate_constraints = (candidate_state or {}).get("constraints", {})

        # Check for opposing intent keywords (e.g. preserve vs expansion, pending vs approved)
        if candidate_intent and task_intent and task_intent != candidate_intent:
            opposing_pairs = [
                ("preserve", "expansion"),
                ("ascending", "descending"),
                ("create", "delete"),
                ("add", "remove"),
                ("enable", "disable"),
                ("include", "exclude"),
            ]
            t_lower = task_intent.lower()
            c_lower = candidate_intent.lower()
            for w1, w2 in opposing_pairs:
                if (w1 in t_lower and w2 in c_lower) or (w2 in t_lower and w1 in c_lower):
                    causal_conflict += 0.60
                    divergent_constraints["opposing_intent"] = (w2, w1)
                    break

        # Check for explicit structural constraint divergence (entity type, temporal scope, status, aggregation, cardinality, sentiment, rank)
        STRUCTURAL_KEYS = {"target_type", "temporal_scope", "status", "aggregation", "cardinality", "sentiment", "rank"}
        for k, v in candidate_constraints.items():
            if k in STRUCTURAL_KEYS and k in task_constraints and task_constraints[k] != v:
                causal_conflict += 0.50
                divergent_constraints[k] = (v, task_constraints[k])

        # Check for counterexamples in candidate contracts
        task_id = str(task_state.get("task_id", ""))
        for contract in candidate.contracts:
            if task_id and task_id in contract.counterexamples:
                causal_conflict += 0.50
                divergent_constraints["counterexample_task"] = (contract.contract_id, task_id)
            if task_intent and any(ce == task_intent for ce in contract.counterexamples):
                causal_conflict += 0.50
                divergent_constraints["counterexample_intent"] = (contract.contract_id, task_intent)
        if task_id and task_id in candidate.structural_stats.get("counterexamples", ()):
            causal_conflict += 0.50
            divergent_constraints["counterexample_task"] = (candidate.schema_id, task_id)

        # Check preconditions in candidate
        missing_preconditions = [
            p for p in candidate.preconditions if not task_state.get(p, False)
        ]
        if missing_preconditions:
            causal_conflict += 0.40 * (len(missing_preconditions) / len(candidate.preconditions))
            divergent_constraints["missing_preconditions"] = (candidate.preconditions, tuple(missing_preconditions))

        if task_schema is not None:
            graph_distance = calculate_graph_distance(task_schema, candidate)
            if graph_distance >= self.causal_threshold:
                causal_conflict = max(causal_conflict, graph_distance)
                divergent_constraints["dag"] = (
                    tuple(edge.as_tuple for edge in candidate.edges),
                    tuple(edge.as_tuple for edge in task_schema.edges),
                )

        causal_conflict = min(1.0, causal_conflict)

        # Strict cognitive separation criterion:
        # Negative transfer ONLY occurs when surface resemblance is high (looks the same),
        # but causal/constraint structure diverges (requires different actions/invariants).
        is_negative_transfer = (
            semantic_sim >= self.semantic_threshold and causal_conflict >= self.causal_threshold
        )

        if is_negative_transfer:
            variant_id = f"{candidate.schema_id}_variant_{task_intent or 'separated'}"
            diff_desc = ", ".join(f"{k}: '{v[0]}' vs '{v[1]}'" for k, v in divergent_constraints.items())
            return PatternSeparationDecision(
                should_separate=True,
                reason=(
                    f"Negative transfer risk: Causal conflict is high ({causal_conflict:.2f} >= "
                    f"{self.causal_threshold:.2f}, semantic_sim={semantic_sim:.2f}). Divergences: [{diff_desc}]."
                ),
                semantic_similarity=semantic_sim,
                causal_distance=causal_conflict,
                suggested_variant_id=variant_id,
                divergent_constraints=divergent_constraints,
            )

        return PatternSeparationDecision(
            should_separate=False,
            reason="Compatible structure: No structural conflict detected.",
            semantic_similarity=semantic_sim,
            causal_distance=causal_conflict,
            suggested_variant_id=None,
            divergent_constraints={},
        )
