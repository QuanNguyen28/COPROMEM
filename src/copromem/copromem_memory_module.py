"""COPROMEM 2.0 Memory Module replacing ReasoningBank's select_memory & induce_memory.

Implements a principled, domain-agnostic memory architecture:
- Dynamic Memory Bank populated via experience, with generic seed guidance.
- Naive RAG (semantic_rag): Cosine/Jaccard similarity retrieval over accumulated memories (exposing negative transfer).
- COPROMEM 2.0 (copromem_v2): Pattern separation and structural plan guidance.
  Browser milestones are prompt guidance until a domain verifier is available.
- Trajectory Induction: Automatically mining procedural insights and invariants from execution traces.
"""

from __future__ import annotations

import json
import logging
import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .bank import StructuralSchemaBank
from .contracts import Contract
from .decomposition import HierarchicalExecutionPlan, RecursiveTaskDecomposer
from .pattern_separation import PatternSeparationEngine, token_jaccard_similarity
from .schema import DecompositionSchema
from .types import (
    CreditAssignmentResult,
    DependencyEdge,
    EpisodicTrace,
    FailureTier,
    HandoffEvent,
    SubtaskNode,
)

logger = logging.getLogger(__name__)


@dataclass
class MemoryInjectionResult:
    """Represents memory content injected into the agent's prompt."""

    arm: str
    injected_text: str
    schema: DecompositionSchema | None = None
    contract: Contract | None = None
    separated: bool = False
    should_veto: bool = False
    alternative_schema: DecompositionSchema | None = None
    should_explore: bool = False


@dataclass
class ProceduralMemoryItem:
    """A generic procedural memory item induced from an agent trajectory."""

    memory_id: str
    intent: str
    title: str
    description: str
    procedure: str
    constraints: dict[str, str] = field(default_factory=dict)
    domain: str = "general"
    success: bool = True
    is_macro: bool = False
    schema_id: str | None = None
    source: str = "observed"


# Domain-agnostic seed guidance; not task-specific evidence.
DEFAULT_PROCEDURAL_MEMORIES: list[ProceduralMemoryItem] = [
    ProceduralMemoryItem(
        memory_id="mem_general_search",
        intent="find or search record, item or entity in collection",
        title="Entity Lookup and Detail Extraction",
        description="Applicable when searching for items, records, or attributes matching target criteria.",
        procedure="Locate the primary search or navigation context, enter the target query, inspect the matching record or entity, and verify that all requested attributes match before reporting.",
        constraints={"target_type": "entity_lookup"},
        domain="general",
        success=True,
        source="generic_seed",
    ),
    ProceduralMemoryItem(
        memory_id="mem_general_filter",
        intent="filter records or metrics by condition and period",
        title="State-Conditioned Filtering and Metric Extraction",
        description="Applicable when querying statistics, counts, or metrics within specific conditions or time ranges.",
        procedure="Access the relevant reporting or records view, apply specified condition or date range constraints, commit state update to refresh records, and verify matching records before extracting metrics.",
        constraints={"target_type": "metric_rank", "scope": "temporal_filter"},
        domain="general",
        success=True,
        source="generic_seed",
    ),
]


def extract_intent_constraints(intent: str) -> dict[str, str]:
    """Extract domain-agnostic entity and condition constraints from intent string."""
    import re
    constraints: dict[str, str] = {}
    intent_lower = intent.lower().strip()

    # 1. Linguistic Target Entity Extraction (domain-agnostic noun phrase following question/extraction verbs)
    intent_no_mod = re.sub(
        r'\b(?:top[- ]?\d+|best[- ]?selling|most|least|highest|lowest|first|second|third|1st|2nd|3rd|newest|oldest|latest|earliest|popular)\b',
        '',
        intent_lower,
    )
    intent_no_mod = re.sub(r'\s+', ' ', intent_no_mod)

    m_count = re.search(r'\b(?:how many|number of|count of|total)\s+([a-zA-Z_\-]+(?:\s+[a-zA-Z_\-]+)?)\b', intent_no_mod)
    if m_count:
        val = m_count.group(1).strip()
        val = re.sub(r'\s+(?:have|has|had|are|is|were|was|in|with|that)$', '', val)
        if val:
            constraints["target_type"] = val
    if "target_type" not in constraints:
        m_which = re.search(
            r'\b(?:what(?:\s+is)?(?:\s+the)?|find(?:\s+the)?|which|show(?:\s+the)?|extract(?:\s+the)?|who(?:\s+is)?(?:\s+the)?|name(?:\s+the)?|tell(?:\s+me)?(?:\s+the)?)\s+([a-zA-Z_\-]+(?:\s+[a-zA-Z_\-]+)?)(?:\s+(?:with|that|who|having|has|had|have|in|for|from|is|was|of|whose|satisfying)|\?|$)',
            intent_no_mod,
        )
        if m_which:
            val = m_which.group(1).strip()
            val = re.sub(r'\s+(?:have|has|had|are|is|were|was|in|with|that)$', '', val)
            if val:
                constraints["target_type"] = val

    # 2. Temporal Scope Extraction (quarters, months, calendar years)
    m_quarter = re.search(r'\b(quarter\s*[1-4]|q[1-4])\b', intent_lower)
    if m_quarter:
        constraints["temporal_scope"] = m_quarter.group(1)
    else:
        for month in ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec"):
            if re.search(rf'\b{month}\b', intent_lower):
                constraints["temporal_scope"] = month
                break
    if "temporal_scope" not in constraints:
        m_year = re.search(r'\b(19\d\d|20\d\d)\b', intent_lower)
        if m_year:
            constraints["temporal_scope"] = m_year.group(1)

    # 3. State / Status Extraction
    m_stat = re.search(r'\b(?:status|state)\s*(?:is|=|:)?\s*["\']?([a-zA-Z_\-]+(?:\s+[a-zA-Z_\-]+)?)["\']?', intent_lower)
    if m_stat:
        constraints["status"] = m_stat.group(1).strip()
    else:
        for status_val in ("not approved", "pending", "approved", "canceled", "cancelled", "complete", "completed", "closed", "processing", "active", "inactive", "enabled", "disabled"):
            if status_val in intent_lower:
                constraints["status"] = status_val
                break

    # 4. Quoted Filter Terms
    m_term = re.search(r'["\']([^"\']+)["\']', intent)
    if m_term:
        constraints["filter_term"] = m_term.group(1).strip()

    # 5. Identifier Extraction
    m_id = re.search(r'\b(?:id|code|number|sku|ref)\s*[:#]?\s*([0-9a-zA-Z_\-]+)', intent_lower)
    if m_id:
        constraints["entity_id"] = m_id.group(1).strip()

    # 6. Sentiment Extraction
    if any(w in intent_lower for w in ("don't like", "dont like", "dislike", "dissatisfied", "negative", "hate", "problem", "issue", "not like", "complaint", "poor", "bad")):
        constraints["sentiment"] = "negative"
    elif any(w in intent_lower for w in ("like", "satisfied", "positive", "love", "good", "recommend", "great", "excellent")):
        constraints["sentiment"] = "positive"

    # 7. Rank / Extremum / Cardinality Extraction
    if re.search(r'\b(2nd|second)\b', intent_lower):
        constraints["rank"] = "2nd"
    elif re.search(r'\b(3rd|third)\b', intent_lower):
        constraints["rank"] = "3rd"
    elif re.search(r'\b(1st|first)\b', intent_lower):
        constraints["rank"] = "1st"

    m_top = re.search(r'\btop[- ]?(\d+)\b', intent_lower)
    if m_top:
        constraints["aggregation"] = "rank"
        constraints["cardinality"] = m_top.group(1)
    elif any(w in intent_lower for w in ("most", "highest", "lowest", "least", "best", "worst", "maximum", "minimum")):
        constraints["aggregation"] = "rank"
        constraints["cardinality"] = "1"
    elif any(w in intent_lower for w in ("number of", "count of", "how many", "total count")):
        constraints["aggregation"] = "count"

    return constraints


class COPROMEMMemoryModule:
    """Unified memory module supporting no_memory, semantic_rag, reasoningbank, and copromem_v2.
    
    Operates without dataset-specific hardcoded strings or cheat hints.
    """

    def __init__(
        self,
        schema_bank: StructuralSchemaBank | None = None,
        memories_path: Path | str | None = None,
        api_key: str | None = None,
        model: str = "google/gemini-2.5-flash",
        include_contract_guidance: bool = False,
    ) -> None:
        self.bank = schema_bank or StructuralSchemaBank()
        self.fast_buffer = self.bank.fast_buffer
        self.pattern_engine = PatternSeparationEngine(semantic_threshold=0.40, causal_threshold=0.35)
        # Library use is offline unless a caller explicitly opts into LLM calls.
        self.decomposer = RecursiveTaskDecomposer(api_key=api_key or "", model=model)
        self._structural_decomposer = RecursiveTaskDecomposer(api_key="", model=model)
        self.include_contract_guidance = include_contract_guidance
        self.memories: list[ProceduralMemoryItem] = list(DEFAULT_PROCEDURAL_MEMORIES)
        self.pending_memories: list[ProceduralMemoryItem] = []

        if memories_path:
            p = Path(memories_path)
            if p.exists():
                self.load_memories(p)

    def load_memories(self, path: Path | str) -> int:
        """Load procedural memories from a JSONL file or directory."""
        p = Path(path)
        loaded = 0
        files = [p] if p.is_file() else list(p.glob("*.jsonl"))
        for f in files:
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    mem = ProceduralMemoryItem(
                        memory_id=data.get("memory_id", f"mem_{len(self.memories)}"),
                        intent=data.get("intent", ""),
                        title=data.get("title", ""),
                        description=data.get("description", ""),
                        procedure=data.get("procedure", data.get("content", "")),
                        constraints=data.get("constraints", {}),
                        domain=data.get("domain", "general"),
                        success=data.get("success", True),
                        is_macro=data.get("is_macro", False),
                        schema_id=data.get("schema_id"),
                        source=data.get("source", "observed"),
                    )
                    self.memories.append(mem)
                    loaded += 1
                except Exception as e:
                    logger.warning("Failed to parse memory line: %s", e)
        return loaded

    def save_memories(self, path: Path | str) -> None:
        """Save current procedural memories to JSONL."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            for mem in self.memories:
                f.write(json.dumps({
                    "memory_id": mem.memory_id,
                    "intent": mem.intent,
                    "title": mem.title,
                    "description": mem.description,
                    "procedure": mem.procedure,
                    "constraints": mem.constraints,
                    "domain": mem.domain,
                    "success": mem.success,
                    "is_macro": mem.is_macro,
                    "schema_id": mem.schema_id,
                    "source": mem.source,
                }) + "\n")

    def add_memory(self, item: ProceduralMemoryItem, *, defer_until_admitted: bool = False) -> None:
        """Keep unreviewed procedures out of slow retrieval until replay admits them."""
        if defer_until_admitted:
            self.pending_memories.append(item)
        else:
            self.memories.append(item)

    def consolidate_offline(self, min_priority: float = 0.20) -> int:
        consolidated = self.bank.consolidate_offline(min_priority=min_priority)
        admitted_ids = {schema.schema_id for schema in self.bank.schemas if schema.status == "admitted"}
        ready = [item for item in self.pending_memories if item.schema_id in admitted_ids]
        self.memories.extend(ready)
        self.pending_memories = [
            item for item in self.pending_memories if item.schema_id not in admitted_ids
        ]
        return consolidated

    def export_state(self) -> dict[str, Any]:
        """Snapshot the complete continual-learning state for benchmark resume."""
        return {
            "memories": [asdict(item) for item in self.memories],
            "pending_memories": [asdict(item) for item in self.pending_memories],
            "schema_bank": self.bank.as_dict(),
        }

    def load_state(self, state: dict[str, Any]) -> None:
        self.memories = [ProceduralMemoryItem(**item) for item in state["memories"]]
        self.pending_memories = [
            ProceduralMemoryItem(**item) for item in state.get("pending_memories", ())
        ]
        self.bank = StructuralSchemaBank.from_dict(state["schema_bank"])
        self.fast_buffer = self.bank.fast_buffer

    def retrieve_memory(
        self,
        arm: str,
        task_id: str,
        intent: str,
        domain: str = "general",
        sites: tuple[str, ...] | list[str] = (),
        start_url: str = "",
        agent_prompt_wrapper: str = "",
    ) -> MemoryInjectionResult:
        """Retrieve memory guidance based on the active arm."""
        if arm == "no_memory":
            return MemoryInjectionResult(arm=arm, injected_text="")

        if arm == "reasoningbank":
            return self._retrieve_reasoningbank(intent, domain)

        if arm == "semantic_rag":
            return self._retrieve_semantic_rag(intent, domain)

        if arm == "copromem_v2":
            result = self._retrieve_copromem_v2(
                task_id, intent, domain, sites, start_url, agent_prompt_wrapper
            )
            _, alternate, explore = self.bank.retrieve_with_anti_lockin(
                tuple(intent.lower().split()),
                {"intent": intent, "domain": domain,
                 "constraints": extract_intent_constraints(intent)},
                semantic_threshold=self.pattern_engine.semantic_threshold,
                task_schema=result.schema,
            )
            result.alternative_schema = (
                alternate if alternate and alternate.schema_id != result.schema.schema_id
                else None
            ) if result.schema else alternate
            result.should_explore = explore
            if result.alternative_schema is not None:
                alternate = result.alternative_schema
                steps = " -> ".join(node.intent for node in alternate.topological_sort())
                result.injected_text += (
                    f"\n## Alternative structural option ({alternate.schema_id}): {steps}. "
                    "Use only if its prerequisites match the active task."
                )
            if result.should_explore:
                if self.include_contract_guidance:
                    result.injected_text += (
                        "\n## Exploration option: If neither stored workflow fits the observed "
                        "state, construct a fresh plan and verify each milestone."
                    )
                else:
                    result.injected_text += (
                        "\n## Exploration option: If neither stored workflow fits the observed "
                        "state, construct a fresh ordered plan."
                    )
            return result

        return MemoryInjectionResult(arm=arm, injected_text="")

    def _retrieve_reasoningbank(self, intent: str, domain: str) -> MemoryInjectionResult:
        """ReasoningBank format: Top retrieved memory item formatted as markdown."""
        if not self.memories:
            return MemoryInjectionResult(arm="reasoningbank", injected_text="")

        query_tokens = tuple(intent.lower().split())
        scored: list[tuple[float, ProceduralMemoryItem]] = []
        for mem in self.memories:
            mem_tokens = tuple(mem.intent.lower().split())
            sim = token_jaccard_similarity(query_tokens, mem_tokens)
            scored.append((sim, mem))
        scored.sort(key=lambda x: x[0], reverse=True)
        _, best_mem = scored[0]

        lines = [
            "# Memory Item",
            f"## Title: {best_mem.title}",
            f"## Content: {best_mem.procedure}",
        ]
        return MemoryInjectionResult(
            arm="reasoningbank",
            injected_text="\n".join(lines).strip(),
            separated=False,
            should_veto=False,
        )

    def _retrieve_semantic_rag(self, intent: str, domain: str) -> MemoryInjectionResult:
        """Naive Semantic RAG: Cosine/Jaccard retrieval based purely on surface query similarity.
        
        Demonstrates negative transfer: Retrieves the highest keyword-overlap memory
        even when causal constraints (e.g. target entity or temporal scope) conflict.
        """
        if not self.memories:
            return MemoryInjectionResult(arm="semantic_rag", injected_text="")

        query_tokens = tuple(intent.lower().split())
        scored: list[tuple[float, ProceduralMemoryItem]] = []

        for mem in self.memories:
            mem_tokens = tuple(mem.intent.lower().split())
            sim = token_jaccard_similarity(query_tokens, mem_tokens)
            scored.append((sim, mem))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_sim, best_mem = scored[0]

        if top_sim <= 0.0:
            return MemoryInjectionResult(arm="semantic_rag", injected_text="")

        lines = [
            "# Memory Item 1: [Naive RAG Unseparated Retrieval]",
            f"## Title: {best_mem.title}",
            f"## Description: {best_mem.description}",
            f"## Content: {best_mem.procedure}",
        ]
        return MemoryInjectionResult(
            arm="semantic_rag",
            injected_text="\n".join(lines).strip(),
            separated=False,
            should_veto=False,
        )

    def _retrieve_copromem_v2(
        self,
        task_id: str,
        intent: str,
        domain: str,
        sites: tuple[str, ...] | list[str],
        start_url: str,
        agent_prompt_wrapper: str = "",
    ) -> MemoryInjectionResult:
        """Retrieve structural plan guidance and filter incompatible memories.
        
        Prevents negative transfer by vetoing candidate memories with conflicting
        causal/constraint structures; BrowserGym milestones are not executable contracts.
        """
        task_cues = tuple(intent.lower().split())
        task_state = {
            "task_id": task_id,
            "intent": intent,
            "domain": domain,
            "sites": list(sites),
            "start_url": start_url,
        }
        task_state["constraints"] = extract_intent_constraints(intent)
        t_constraints = task_state["constraints"]
        target_cardinality = t_constraints.get("cardinality")

        # Construct the current graph before comparing it with learned candidates.
        is_compound = self.decomposer.is_compound(
            intent=intent, benchmark_context=agent_prompt_wrapper
        )
        plan = self._structural_decomposer.decompose(
            intent=intent, memories=(),
            benchmark_context=agent_prompt_wrapper,
            include_contract_guidance=self.include_contract_guidance,
        )
        schema = self._get_or_create_default_schema(
            domain, task_cues, plan=plan, constraints=t_constraints
        )
        current_schema = schema
        contract = None

        # Step 1: Candidate Memory Retrieval & Pattern Separation Evaluation
        candidate_mem = None
        top_sim = 0.0
        sep_decision = None
        conflict_schema: DecompositionSchema | None = None
        selected_schema: DecompositionSchema | None = None

        if self.memories:
            scored: list[tuple[float, ProceduralMemoryItem]] = []
            for mem in self.memories:
                if not mem.success:
                    continue
                if mem.source == "generic_seed":
                    continue
                if mem.domain not in ("general", domain):
                    continue
                mem_tokens = tuple(mem.intent.lower().split())
                sim = token_jaccard_similarity(task_cues, mem_tokens)
                scored.append((sim, mem))
            scored.sort(key=lambda x: x[0], reverse=True)
            if scored:
                top_sim = scored[0][0]
            for similarity, mem in scored:
                if similarity < self.pattern_engine.semantic_threshold:
                    break
                cand_schema = next(
                    (s for s in self.bank.schemas if s.schema_id == mem.schema_id
                     and s.status == "admitted"),
                    None,
                )
                if cand_schema is None:
                    cand_schema = DecompositionSchema(
                        schema_id=f"unbound_{mem.memory_id}",
                        task_family=domain,
                        semantic_cues=tuple(mem.intent.lower().split()),
                        nodes=(SubtaskNode("goal", "agent", "execute_goal"),),
                        edges=(),
                    )
                decision = self.pattern_engine.evaluate(
                    task_cues=task_cues,
                    task_state=task_state,
                    candidate=cand_schema,
                    candidate_state={"intent": mem.intent, "constraints": mem.constraints},
                    task_schema=schema if mem.schema_id and cand_schema.status == "admitted" else None,
                )
                if decision.should_separate:
                    if sep_decision is None:
                        sep_decision = decision
                        if cand_schema.status == "admitted":
                            conflict_schema = cand_schema
                    continue
                candidate_mem = mem
                top_sim = similarity
                sep_decision = None
                if mem.schema_id and cand_schema.status == "admitted":
                    selected_schema = cand_schema
                break

        should_veto = sep_decision.should_separate if sep_decision else False
        if should_veto and conflict_schema is not None:
            counterexamples = set(conflict_schema.structural_stats.get("counterexamples", ()))
            counterexamples.add(task_id)
            updated = conflict_schema.with_stats(counterexamples=sorted(counterexamples))
            self.bank.schemas = [
                updated if item.schema_id == updated.schema_id else item
                for item in self.bank.schemas
            ]
        allowed_memories = [candidate_mem] if candidate_mem is not None else []
        plan = self.decomposer.decompose(
            intent=intent, memories=allowed_memories,
            benchmark_context=agent_prompt_wrapper,
            include_contract_guidance=self.include_contract_guidance,
        )
        schema = self._get_or_create_default_schema(
            domain, task_cues, plan=plan, constraints=t_constraints
        )
        if selected_schema is not None:
            schema = selected_schema
        # Step 2: Expose a diverse admitted alternative when one exists.
        _, alternative_schema, should_explore = self.bank.retrieve_with_anti_lockin(
            task_cues, task_state,
            semantic_threshold=self.pattern_engine.semantic_threshold,
            task_schema=current_schema,
        )

        # Synthesize Differentiated Contract text if negative transfer divergence detected
        contract_text = ""
        if should_veto and sep_decision and self.include_contract_guidance:
            diffs = sep_decision.divergent_constraints or {}
            diff_desc = ", ".join(f"{k}: '{v[0]}' -> '{v[1]}'" for k, v in diffs.items()) or sep_decision.reason

            target_scope = t_constraints.get("target_type", "target entity")
            target_status = t_constraints.get("status")
            target_period = t_constraints.get("temporal_scope")
            target_aggregation = t_constraints.get("aggregation")

            contract_lines = [
                "# Memory Item: [COPROMEM 2.0 Differentiated Contract]",
                f"## Alert: Divergent constraint detected ({diff_desc}). Conflicting procedural assumptions inhibited.",
                "## Complete Constraint Verification Guard: An observation may only be used if ALL specified constraints (criteria, state, metric scope) are explicitly verified in the active view. If any constraint is unverified or ambiguous, you MUST actively perform the necessary scoping/filtering operations before concluding.",
            ]

            if "sentiment" in diffs:
                target_sentiment = t_constraints.get("sentiment", "target sentiment")
                contract_lines.extend([
                    f"## Target Constraint: Required sentiment is '{target_sentiment}'.",
                    "## Precondition: Locate the relevant detail or text content view for the target entity.",
                    f"## Execution Invariant: Inspect text entries expressing '{target_sentiment}' sentiment. Inhibit entries with opposite sentiment.",
                    f"## Verification Postcondition: Verify extracted content strictly reflects '{target_sentiment}' aspects.",
                    "## Recovery Route: If current entries reflect opposite sentiment, inspect other entries or records.",
                ])
            elif "rank" in diffs:
                target_rank = t_constraints.get("rank", "target rank")
                contract_lines.extend([
                    f"## Target Constraint: Target ranking position is '{target_rank}' place (NOT top 1).",
                    "## Precondition: Access the ordered or ranked records collection.",
                    f"## Execution Invariant: Order records by target metric and locate entry at rank '{target_rank}'.",
                    f"## Verification Postcondition: Verify the extracted entity is strictly at position '{target_rank}', not the 1st place entity.",
                    "## Recovery Route: Inspect the record at the specified rank position.",
                ])
            elif target_cardinality and int(target_cardinality) > 1 and "cardinality" in diffs:
                contract_lines.extend([
                    f"## Target Constraint: Exactly {target_cardinality} distinct items requested.",
                    "## Precondition: Locate the relevant ranking or ordered records summary.",
                    f"## Execution Invariant: Extract all top {target_cardinality} items in order (format: Item 1, Item 2, ...).",
                    f"## Verification Postcondition: Verify the final answer list contains exactly {target_cardinality} distinct entity names, not just 1.",
                    "## Recovery Route: If fewer items are extracted, check subsequent entries in the ranking list.",
                ])
            elif target_aggregation == "count":
                scope_desc = target_scope + (f" with status '{target_status.title()}'" if target_status else "") + (f" for '{target_period}'" if target_period else "")
                contract_lines.extend([
                    f"## Target Constraint: Total count of {scope_desc}.",
                    "## Precondition: Access the domain record source matching target criteria.",
                    "## Execution Invariant: Configure all required state/filter criteria and commit state update to refresh records.",
                    "## Verification Postcondition: Extract the total matching record count (verify total count summary rather than counting visible subset rows). If zero records found or the collection is empty, count is strictly 0. Never report the baseline or unfiltered total count shown in pagination metadata.",
                    "## Recovery Route: If total count is ambiguous, inspect the view header or summary metadata for the total set count. Report count 0 if no records match criteria.",
                ])
            elif target_status:
                contract_lines.extend([
                    f"## Target Constraint: Required state '{target_status}'.",
                    f"## Precondition: Set environment state parameter to '{target_status}'.",
                    "## Execution Invariant: Commit state mutation / trigger update to transition environment to the target state.",
                    f"## Verification Postcondition: Verify observed state reflects the active '{target_status}' criterion before extracting output.",
                    "## Recovery Route: If observation reflects stale or uncommitted state, re-execute state commit action.",
                ])
            elif "target_type" in diffs or target_period:
                scope_desc = f"'{target_scope}'" + (f" for '{target_period}'" if target_period else "")
                contract_lines.extend([
                    f"## Target Constraint: Target scope {scope_desc}.",
                    f"## Precondition: Access the domain record source or collection for {scope_desc}.",
                    f"## Execution Invariant: Extract strictly the requested attribute value ({target_scope}), NOT the full parent container or auxiliary metadata.",
                    f"## Verification Postcondition: Verify the output is strictly the requested attribute ({target_scope}) matching all query criteria.",
                    "## Recovery Route: If target attribute is absent in current view, inspect related detail records.",
                ])
            else:
                contract_lines.extend([
                    f"## Target Constraint: Target scope {target_scope}.",
                    "## Precondition: Locate the relevant domain view and configure criteria inputs.",
                    "## Execution Invariant: Commit parameter changes to update observation.",
                    f"## Verification Postcondition: Verify displayed records match query constraints before reading value.",
                    "## Recovery Route: If view is unrefreshed, re-commit parameters.",
                ])

            if target_cardinality == "1":
                contract_lines.append("## Cardinality Invariant: Exactly 1 single top item requested. Output only the top 1 entity name, not multiple tied items.")
            contract_lines.append("## Output Invariant: Output strictly the exact extracted value, count, or entity name without conversational filler words or sentence wrappers (e.g. send_msg_to_user('value')).")

            contract_text = "\n".join(contract_lines).strip()

        # Step 3: Compound Task Factorization (HTN Decomposition)
        if is_compound:
            decomp_plan = plan
            injected_parts = []
            if contract_text:
                injected_parts.append(contract_text)
            if decomp_plan.injected_prompt_text:
                injected_parts.append(decomp_plan.injected_prompt_text)

            return MemoryInjectionResult(
                arm="copromem_v2",
                injected_text="\n\n".join(injected_parts).strip(),
                schema=schema,
                contract=contract,
                separated=should_veto,
                should_veto=should_veto,
                alternative_schema=alternative_schema,
                should_explore=should_explore,
            )

        # Step 4: Atomic Tasks
        # If separated / vetoed, return Differentiated Contract
        if should_veto and contract_text:
            return MemoryInjectionResult(
                arm="copromem_v2",
                injected_text=contract_text,
                schema=schema,
                contract=contract,
                separated=True,
                should_veto=True,
            )

        # Cold start (no memories yet)
        if not self.memories:
            decomp_plan = plan
            if decomp_plan.injected_prompt_text:
                return MemoryInjectionResult(
                    arm="copromem_v2",
                    injected_text=decomp_plan.injected_prompt_text,
                    schema=schema,
                    contract=contract,
                    separated=False,
                    should_veto=False,
                )
            injected = ["# Task Execution Guidance: [Autonomous Exploration]"]
            if self.include_contract_guidance:
                injected.extend([
                    f"- Precondition: {contract.precondition if contract else 'verify target context'}",
                    f"- Postcondition Invariant: {contract.postcondition if contract else 'validate extracted entity matches user constraints'}",
                    "- Complete Constraint Verification Guard: An observation may only be used if ALL specified constraints (criteria, state, metric scope) are explicitly verified in the active view. If any constraint is unverified or ambiguous, you MUST actively perform the necessary scoping/filtering operations before concluding.",
                ])
            return MemoryInjectionResult(
                arm="copromem_v2",
                injected_text="\n".join(injected),
                schema=schema,
                contract=contract,
                separated=False,
                should_veto=False,
            )

        # Low similarity / orthogonal candidate memory (no past memory directly matches)
        if candidate_mem is None or top_sim < self.pattern_engine.semantic_threshold:
            decomp_plan = plan
            if decomp_plan.injected_prompt_text:
                return MemoryInjectionResult(
                    arm="copromem_v2",
                    injected_text=decomp_plan.injected_prompt_text,
                    schema=schema,
                    contract=contract,
                    separated=False,
                    should_veto=False,
                )
            target_scope = task_state.get("constraints", {}).get("target_type", "target query")
            injected = [
                "# Task Execution Guidance: [Novel Goal - Multi-Stage Decomposition]",
            ]
            if self.include_contract_guidance:
                injected.extend([
                    f"## Target Scope: {target_scope}",
                    f"## Precondition: Access domain record source for '{target_scope}'. Locate relevant collection or detail records.",
                    f"## Verification Invariant: {contract.postcondition if contract else 'Validate extracted entity strictly matches user constraints.'}",
                    "## Complete Constraint Verification Guard: An observation may only be used if ALL specified constraints (criteria, state, metric scope) are explicitly verified in the active view. If any constraint is unverified or ambiguous, you MUST actively perform the necessary scoping/filtering operations before concluding.",
                ])
                if target_cardinality == "1":
                    injected.append("## Cardinality Invariant: Exactly 1 single top item requested. Output only the top 1 entity name, not multiple tied items.")
            return MemoryInjectionResult(
                arm="copromem_v2",
                injected_text="\n".join(injected),
                schema=schema,
                contract=contract,
                separated=False,
                should_veto=False,
            )

        # Compatible procedure
        injected = [
            f"# Memory Item: [COPROMEM 2.0 Observed Successful Procedure]",
            f"## Title: {candidate_mem.title}",
            f"## Structural Flow: {candidate_mem.procedure}",
        ]
        if self.include_contract_guidance:
            injected.extend([
                f"## Applicable Scope: {task_state.get('constraints', {}).get('target_type', 'target query')}",
                f"## Precondition: {contract.precondition if contract else 'Verify page context and input fields.'}",
                f"## Verification Invariant: {contract.postcondition if contract else 'Confirm extracted data matches exact requested entity and criteria.'}",
                "## Complete Constraint Verification Guard: An observation may only be used if ALL specified constraints (criteria, state, metric scope) are explicitly verified in the active view. If any constraint is unverified or ambiguous, you MUST actively perform the necessary scoping/filtering operations before concluding.",
            ])
            if target_cardinality == "1":
                injected.append("## Cardinality Invariant: Exactly 1 single top item requested. Output only the top 1 entity name, not multiple tied items.")
        return MemoryInjectionResult(
            arm="copromem_v2",
            injected_text="\n".join(injected),
            schema=schema,
            contract=contract,
            separated=False,
            should_veto=False,
        )

    def _get_or_create_default_schema(
        self,
        domain: str,
        cues: tuple[str, ...],
        plan: HierarchicalExecutionPlan | None = None,
        constraints: dict[str, str] | None = None,
    ) -> DecompositionSchema:
        """Cache the observable milestone graph without inventing an executable verifier."""
        if plan is None:
            nodes = (SubtaskNode("goal", "agent", "execute_goal"),)
            edges: tuple[DependencyEdge, ...] = ()
            plan_type = "unbound"
        else:
            nodes = tuple(
                SubtaskNode(f"step_{idx}", "agent", goal.description)
                for idx, goal in enumerate(plan.subgoals, 1)
            )
            edges = tuple(
                DependencyEdge(nodes[idx].node_id, nodes[idx + 1].node_id)
                for idx in range(len(nodes) - 1)
            )
            plan_type = plan.plan_type
        signature = json.dumps(
            {"domain": domain, "plan_type": plan_type,
             "constraints": constraints or {},
             "roles": [node.role for node in nodes],
             "edges": [edge.as_tuple for edge in edges]},
            sort_keys=True,
        )
        schema_id = f"schema_{domain}_{hashlib.sha256(signature.encode()).hexdigest()[:12]}"
        existing = next((s for s in self.bank.schemas if s.schema_id == schema_id), None)
        if existing is not None:
            return existing
        schema = DecompositionSchema(
            schema_id=schema_id,
            task_family=f"Domain_{domain}",
            semantic_cues=cues,
            nodes=nodes,
            edges=edges,
            structural_stats={
                "execution_count": 0,
                "transfer_reliability": 0.0,
                "constraints": dict(constraints or {}),
                "source_intent": " ".join(cues),
            },
        )
        # A new plan remains a candidate until offline evidence is reviewed.
        self.bank.schemas.append(schema)
        return schema

    def record_episode(
        self,
        task_id: str,
        arm: str,
        success: bool,
        task_state: dict[str, Any],
        schema: DecompositionSchema | dict[str, Any] | None,
        handoffs: list[HandoffEvent] | tuple[HandoffEvent, ...] = (),
    ) -> CreditAssignmentResult | None:
        """Record episodic trace and consolidate schema statistics."""
        if schema is None:
            s_id = None
            rel = 0.0
        elif isinstance(schema, dict):
            s_id = schema.get("schema_id", f"schema_{task_state.get('domain', 'general')}")
            stats = schema.get("structural_stats", {})
            rel = stats.get("transfer_reliability", 0.90) if isinstance(stats, dict) else 0.90
        else:
            s_id = getattr(schema, "schema_id", f"schema_{task_state.get('domain', 'general')}")
            rel = getattr(schema, "transfer_reliability", 0.90)

        credit_result: CreditAssignmentResult | None = None
        if not success:
            resolved_contracts: set[str] = set()
            failed = None
            for event in reversed(handoffs):
                for result in event.verifier_results:
                    if result.passed:
                        resolved_contracts.add(result.contract_id)
                    elif result.contract_id not in resolved_contracts:
                        failed = (event, result)
                        break
                if failed:
                    break
            if failed:
                event, result = failed
                credit_result = CreditAssignmentResult(
                    tier=FailureTier.HANDOFF_VIOLATION,
                    responsible_entity=f"{event.interface}:{result.contract_id}",
                    reason=result.reason,
                    suggested_patch=f"Repair the {event.source_role} artifact and verify again.",
                    confidence=0.9,
                )
            else:
                credit_result = CreditAssignmentResult(
                    tier=FailureTier.UNKNOWN,
                    responsible_entity="unknown",
                    reason="No failed observable handoff verifier identifies the cause.",
                    suggested_patch="Collect a boundary artifact and verifier result before structural repair.",
                    confidence=0.0,
                )
        trace = EpisodicTrace(
            trace_id=f"trace_{task_id}_{arm}",
            task_id=task_id,
            task_state=task_state,
            schema_id=s_id,
            handoff_events=tuple(handoffs),
            success=success,
            credit_result=credit_result,
            surprise=1.0 if not success else 0.0,
            uncertainty=round(max(0.0, 1.0 - rel), 3),
        )
        self.fast_buffer.add_trace(trace)

        return credit_result
