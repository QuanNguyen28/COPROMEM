"""Recursive Hierarchical Task Network (HTN) Decomposition Engine for COPROMEM.

Implements domain-agnostic task decomposition:
1. Consolidated Macro Planning (Warm Memory):
   If a matching macro-routine is learned in memory, factors compound tasks into
   an optimal 2-step macro-plan: [Learned Macro Routine] + [Target Delta / Adaptation].
2. Recursive Divide-and-Conquer Fallback (Cold Memory / Unlearned Hard Task):
   If no matching macro-routine exists, recursively breaks down compound tasks
   until all leaf sub-goals are atomic, enabling the agent to explore ("tự mày mò")
   and solve sub-goals step-by-step with verified milestone invariants.
3. Checkpoint Invariants:
   Strictly guards against premature terminal submissions (send_msg_to_user)
   until all milestone postconditions are verified.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from .pattern_separation import token_jaccard_similarity

logger = logging.getLogger(__name__)


@dataclass
class SubGoal:
    """An operational sub-goal within a hierarchical execution plan."""

    subgoal_id: str
    description: str
    is_atomic: bool = True
    bound_memory_id: str | None = None
    bound_memory_title: str | None = None
    bound_memory_proc: str | None = None
    precondition: str = ""
    postcondition: str = ""
    invariants: list[str] = field(default_factory=list)
    recovery_route: str = ""
    children: list[SubGoal] = field(default_factory=list)
    depth: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "subgoal_id": self.subgoal_id,
            "description": self.description,
            "is_atomic": self.is_atomic,
            "bound_memory_id": self.bound_memory_id,
            "bound_memory_title": self.bound_memory_title,
            "bound_memory_proc": self.bound_memory_proc,
            "precondition": self.precondition,
            "postcondition": self.postcondition,
            "invariants": self.invariants,
            "recovery_route": self.recovery_route,
            "children": [c.to_dict() for c in self.children],
            "depth": self.depth,
        }


@dataclass
class HierarchicalExecutionPlan:
    """A complete hierarchical plan containing milestones and checkpoint contracts."""

    task_intent: str
    plan_type: str  # "macro_two_step", "recursive_atomic", "direct_atomic"
    subgoals: list[SubGoal] = field(default_factory=list)
    milestones: list[str] = field(default_factory=list)
    checkpoint_invariants: list[str] = field(default_factory=list)
    injected_prompt_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_intent": self.task_intent,
            "plan_type": self.plan_type,
            "subgoals": [s.to_dict() for s in self.subgoals],
            "milestones": self.milestones,
            "checkpoint_invariants": self.checkpoint_invariants,
            "injected_prompt_text": self.injected_prompt_text,
        }


def _call_openrouter_json(
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 768,
    temperature: float = 0.0,
    usage_sink: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any] | None:
    """Call OpenRouter LLM expecting a structured JSON response."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = json.dumps(
        {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/QuanNguyen28/COPROMEM",
            "X-Title": "COPROMEM-Task-Decomposer",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if usage_sink is not None:
                usage_sink(data.get("usage") or {})
            content = data["choices"][0]["message"]["content"]
            # Clean JSON if wrapped in markdown code blocks
            m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
            raw_json = m.group(1) if m else content
            return json.loads(raw_json)
    except Exception as e:
        logger.warning("OpenRouter decomposition JSON call failed: %s", e)
        return None


def _get_api_key(api_key: str | None = None) -> str:
    """Retrieve API key from argument, environment, or .env file."""
    if api_key is not None:
        return api_key
    if os.environ.get("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"].strip()
    from pathlib import Path
    env_file = Path(".env")
    if env_file.exists():
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("OPENROUTER_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            pass
    return ""


_SUBTASK_STOPWORDS = {
    "a", "an", "the", "in", "on", "at", "by", "for", "with", "about", "against",
    "between", "into", "through", "during", "before", "after", "above", "below",
    "to", "from", "up", "down", "out", "off", "over", "under", "again",
    "further", "then", "once", "here", "there", "when", "where", "why", "how",
    "all", "any", "both", "each", "few", "more", "most", "other", "some", "such",
    "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "can", "will", "just", "don", "should", "now", "and", "or", "phase", "step",
    "milestone", "subgoal", "goal"
}


def _extract_semantic_tokens(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z]{3,}", text.lower())
    res = set()
    for w in words:
        if w in _SUBTASK_STOPWORDS:
            continue
        res.add(w)
        if w.endswith("s") and len(w) > 4:
            res.add(w[:-1])
        if w.endswith("ed") and len(w) > 5:
            res.add(w[:-2])
        if w.endswith("ing") and len(w) > 6:
            res.add(w[:-3])
        if w.endswith("tion") and len(w) > 7:
            res.add(w[:-4])
    return res


class RecursiveTaskDecomposer:
    """Domain-agnostic recursive HTN decomposition engine.

    Decomposes task intents into hierarchical milestone contracts:
    - Factors warm memories into 2-step macro plans: [Learned Routine] + [Delta]
    - Recursively divides cold/unlearned compound tasks into atomic leaf milestones
    - Enforces checkpoint invariants forbidding premature send_msg_to_user
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "google/gemini-2.5-flash",
        max_depth: int = 3,
        similarity_threshold: float = 0.45,
    ) -> None:
        self.api_key = _get_api_key(api_key)
        self.model = model
        self.max_depth = max_depth
        self.similarity_threshold = similarity_threshold
        self._plan_cache: dict[str, HierarchicalExecutionPlan] = {}
        self._complexity_cache: dict[str, tuple[bool, str]] = {}
        self.api_cost_usd = 0.0
        self.api_prompt_tokens = 0
        self.api_completion_tokens = 0

    def _record_usage(self, usage: dict[str, Any]) -> None:
        self.api_cost_usd += float(usage.get("cost") or 0.0)
        self.api_prompt_tokens += int(usage.get("prompt_tokens") or 0)
        self.api_completion_tokens += int(usage.get("completion_tokens") or 0)

    def assess_complexity(
        self,
        intent: str,
        benchmark_context: str = "Autonomous agent environment with dashboards, data collections, state filters, and entity views",
    ) -> tuple[bool, str]:
        """Domain-agnostic complexity assessment using LLM evaluation with caching and syntactic fallback based on Constraint Composition."""
        cache_key = hashlib.sha256(
            json.dumps([intent.strip().lower(), benchmark_context], sort_keys=True).encode("utf-8")
        ).hexdigest()
        if cache_key in self._complexity_cache:
            return self._complexity_cache[cache_key]

        # 1. LLM Semantic Complexity Assessment if API key is configured
        if self.api_key:
            system_prompt = (
                "You are an expert Autonomous Agent Cognitive Task Complexity Classifier.\n"
                f"Operating Environment Context: {benchmark_context}.\n\n"
                "Classify the user intent into one of two complexity categories based on the Constraint Composition Principle:\n\n"
                "- ATOMIC (is_compound: false): The intent specifies a single direct operation that can be resolved in a single primitive step without sequential dependencies or state transformations.\n"
                "  Characteristics: Direct lookup of an entity by ID or name; reading a single unconditioned metric; or retrieving a pre-existing unconditioned listing.\n\n"
                "- COMPOUND (is_compound: true): The intent specifies a compositional multi-stage constraint pipeline with sequential dependencies:\n"
                "  1. Scope Restriction -> Extremum/Order Selection -> Attribute Projection: Filtering by a prerequisite state/condition, ordering or finding an extremum (e.g. most recent, oldest, newest, highest, lowest, earliest, rank-K), and extracting a secondary target attribute.\n"
                "  2. Multi-Context Chaining: Discovering an entity/token in one context, and using it to perform an action or query in another context.\n"
                "  3. Aggregation across Collections: Tallying, summing, or comparing metrics across multiple records or time intervals.\n"
                "  4. Conditioned State Mutation: Verifying specific criteria before updating, creating, or notifying entities.\n\n"
                "Return strictly JSON: {\"is_compound\": bool, \"rationale\": str}"
            )
            user_prompt = f"User Intent: \"{intent}\"\nEvaluate whether this intent is atomic or compound."
            resp = _call_openrouter_json(
                api_key=self.api_key,
                model=self.model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=200,
                temperature=0.0,
                usage_sink=self._record_usage,
            )
            if resp and "is_compound" in resp:
                is_comp = bool(resp["is_compound"])
                rationale = str(resp.get("rationale", ""))
                self._complexity_cache[cache_key] = (is_comp, rationale)
                return is_comp, rationale

        # 2. Pure Domain-Agnostic Syntactic Fallback (Zero Benchmark Tokens)
        intent_lower = intent.lower()

        # Multi-stage sequential workflow markers
        if any(c in intent_lower for c in (" and then ", " after that ", " followed by ", " then update ", " then send ", " then find ", " then notify ")):
            res = (True, "Syntactic fallback: Multi-stage sequential workflow conjunction.")
            self._complexity_cache[cache_key] = res
            return res

        # Multi-stage aggregation across grouped collections / time intervals
        if bool(re.search(r"\b(?:monthly|daily|weekly|yearly|annual)\s+(?:count|sum|total|average|breakdown)\b", intent_lower)):
            res = (True, "Syntactic fallback: Multi-period time-series sequence assembly.")
            self._complexity_cache[cache_key] = res
            return res

        if bool(re.search(r"\bfrom\s+\w+\s+to\s+\w+\s+(?:in|\d{4})\b", intent_lower)):
            res = (True, "Syntactic fallback: Cross-interval temporal aggregation.")
            self._complexity_cache[cache_key] = res
            return res

        if bool(re.search(r"\b(?:average|avg|sum|total)\s+\w+\s+of\s+(?:closed|resolved|completed|pending|active|inactive|all)\b", intent_lower)):
            res = (True, "Syntactic fallback: Conditioned aggregation across records.")
            self._complexity_cache[cache_key] = res
            return res

        # Multi-stage Compositional constraint pipeline:
        # 1. Scope qualification (subordinate relative clauses, historical span, temporal intervals)
        has_subordinate_scope = bool(re.search(
            r"\b(?:who\s+have|who\s+has|that\s+have|that\s+has|that\s+are|in\s+(?:the\s+)?history|all\s+time|entire\s+history|among\s+all)\b",
            intent_lower
        ))
        has_extremum = bool(re.search(
            r"\b(?:most\s+recent|oldest|newest|latest|earliest|highest|lowest|second\s+most|2nd\s+most|most\s+number|least\s+number|last\s+\d+|top\s+\d+|most\s+\w+|least\s+\w+)\b",
            intent_lower
        ))
        if has_subordinate_scope and (has_extremum or "completed" in intent_lower):
            res = (True, "Syntactic fallback: Compositional pipeline (Scope Qualification + Extremum/Ordering).")
            self._complexity_cache[cache_key] = res
            return res

        # 2. State-qualified entity following an extremum/aggregation:
        # e.g., "most recent cancelled order", "oldest pending transaction", "oldest complete order", "last 5 completed orders"
        has_state_qualified_extremum = bool(re.search(
            r"\b(?:most\s+recent|oldest|newest|latest|earliest|highest|lowest|last\s+\d+|first\s+\d+)\s+(?:\w+ed|\w+ing|closed|open|pending|complete|active|inactive|paid|unpaid|valid|invalid)\s+\w+",
            intent_lower
        ))
        if has_state_qualified_extremum:
            res = (True, "Syntactic fallback: Compositional pipeline (State Restriction + Extremum/Ordering).")
            self._complexity_cache[cache_key] = res
            return res

        # Cross-record metric aggregation over restricted subsets (e.g. "total payment of the last 5...")
        if bool(re.search(r"\b(?:total|sum|average|count)\s+\w+\s+of\s+(?:the\s+)?(?:last|top|first)\b", intent_lower)):
            res = (True, "Syntactic fallback: Cross-record aggregation over bounded subset.")
            self._complexity_cache[cache_key] = res
            return res

        res = (False, "Default: Atomic single-objective operational retrieval.")
        self._complexity_cache[cache_key] = res
        return res

    def is_compound(self, intent: str, benchmark_context: str = "") -> bool:
        """Domain-agnostic check whether intent is compound (multi-stage / cross-record aggregation)."""
        ctx = benchmark_context or "Autonomous agent environment with dashboards, data collections, state filters, and entity views"
        is_comp, _ = self.assess_complexity(intent, ctx)
        return is_comp

    def is_atomic(self, intent: str, benchmark_context: str = "") -> bool:
        """Return True if intent is an operational single-goal task that should not be decomposed."""
        return not self.is_compound(intent, benchmark_context)

    def find_matching_macro_schema(
        self,
        intent: str,
        memories: Sequence[Any],
    ) -> tuple[Any | None, float, dict[str, str]]:
        """Find if a consolidated macro-routine exists in memory using domain-agnostic token overlap.

        Returns (matching_memory, similarity_score, divergent_constraints).
        """
        if not memories:
            return None, 0.0, {}

        query_tokens = set(re.findall(r"\w+", intent.lower()))
        STOPWORDS = {"what", "is", "the", "in", "of", "and", "a", "an", "to", "for", "from", "by", "that", "this", "my", "our", "me", "show", "tell", "list", "get", "find"}
        content_query = {w for w in query_tokens if w not in STOPWORDS and len(w) > 2}

        best_mem = None
        best_sim = 0.0

        for mem in memories:
            mem_intent = getattr(mem, "intent", "")
            mem_tokens = set(re.findall(r"\w+", mem_intent.lower()))
            content_mem = {w for w in mem_tokens if w not in STOPWORDS and len(w) > 2}
            if not content_query or not content_mem:
                continue

            intersection = content_query & content_mem
            union = content_query | content_mem
            sim = len(intersection) / len(union) if union else 0.0

            # Procedural family match: shared core operational content words
            if len(intersection) >= 2 and (len(intersection) / max(len(content_query), 1)) >= 0.40:
                sim = max(sim, 0.65)

            if sim > best_sim:
                best_sim = sim
                best_mem = mem

        if best_mem and best_sim >= self.similarity_threshold:
            # Extract divergent constraints (deltas)
            diffs: dict[str, str] = {}
            target_mem_intent = getattr(best_mem, "intent", "").lower()
            intent_lower = intent.lower()

            # Rank divergence (1st vs 2nd vs 3rd)
            for rk in ["1st", "2nd", "3rd", "first", "second", "third"]:
                if rk in intent_lower and rk not in target_mem_intent:
                    diffs["rank"] = f"target specifies '{rk}' vs memory '{target_mem_intent[:30]}'"
            # Status divergence (completed vs pending vs canceled, etc.)
            for st in ["completed", "pending", "canceled", "approved", "not approved", "open", "closed"]:
                if st in intent_lower and st not in target_mem_intent:
                    diffs["status"] = f"target requires status '{st}'"
            # Temporal scope divergence (years)
            years = re.findall(r"\b20\d\d\b", intent_lower)
            mem_years = re.findall(r"\b20\d\d\b", target_mem_intent)
            if years and mem_years and years != mem_years:
                diffs["temporal_scope"] = f"target year '{years[0]}' vs memory year '{mem_years[0]}'"

            # Cardinality divergence
            card_match = re.search(r"\b(?:last|top|first)\s*(\d+)\b", intent_lower)
            mem_card_match = re.search(r"\b(?:last|top|first)\s*(\d+)\b", target_mem_intent)
            if card_match and mem_card_match and card_match.group(1) != mem_card_match.group(1):
                diffs["cardinality"] = f"target count '{card_match.group(1)}' vs memory '{mem_card_match.group(1)}'"

            return best_mem, best_sim, diffs

        return None, best_sim, {}

    def _find_matching_subtask_memory(
        self,
        subgoal_desc: str,
        memories: Sequence[Any],
        task_intent: str = "",
        threshold: float = 0.25,
    ) -> tuple[Any | None, float]:
        """Find a memory item that addresses this specific subtask milestone."""
        if not memories:
            return None, 0.0
        t_sub = _extract_semantic_tokens(subgoal_desc)
        t_goal = _extract_semantic_tokens(task_intent)
        scored: list[tuple[float, Any]] = []
        for mem in memories:
            proc = getattr(mem, "procedure", "")
            m_intent = getattr(mem, "intent", "")
            m_desc = getattr(mem, "description", "")
            m_const = getattr(mem, "constraints", {})
            t_proc = _extract_semantic_tokens(proc)
            t_m_intent = _extract_semantic_tokens(m_intent)
            t_m_desc = _extract_semantic_tokens(m_desc)
            t_const = set()
            if isinstance(m_const, dict):
                for k, v in m_const.items():
                    t_const.update(_extract_semantic_tokens(f"{k} {v}"))
            t_mem_all = t_proc | t_m_intent | t_m_desc | t_const
            context_overlap = t_goal & t_mem_all
            t_mem_actions = (t_proc | t_m_intent | t_m_desc) - t_goal
            action_overlap = t_sub & t_mem_actions
            if len(action_overlap) >= 1 and (len(context_overlap) >= 1 or not t_goal):
                denom = max(len(t_proc | t_m_intent), 1)
                score = (len(action_overlap) + len(context_overlap)) / denom
                if score >= threshold:
                    scored.append((score, mem))
        scored.sort(key=lambda x: x[0], reverse=True)
        if scored:
            return scored[0][1], scored[0][0]
        return None, 0.0

    def decompose(
        self,
        intent: str,
        memories: Sequence[Any] = (),
        benchmark_context: str = "Autonomous agent environment with dashboards, data collections, state filters, and entity views",
        current_depth: int = 0,
        include_contract_guidance: bool = False,
    ) -> HierarchicalExecutionPlan:
        """Execute recursive HTN decomposition.

        Formulation:
        Decompose(T, M, d) =
          - Leaf(T) if IsAtomic(T) or d >= d_max
          - [M_k, Delta(T)] if matching macro-routine M_k exists (2-step macro plan)
          - Union(Decompose(S_i, M, d+1)) otherwise (recursive atomic fallback with subtask memory binding)
        """
        memory_signature = [
            (getattr(memory, "memory_id", None), getattr(memory, "intent", None),
             getattr(memory, "procedure", None), getattr(memory, "constraints", None))
            for memory in memories
        ]
        cache_key = hashlib.sha256(json.dumps(
            [intent, benchmark_context, current_depth, memory_signature, include_contract_guidance],
            sort_keys=True, default=str,
        ).encode("utf-8")).hexdigest()
        if cache_key in self._plan_cache:
            return self._plan_cache[cache_key]

        # Case 1: Atomic task (Leaf)
        if self.is_atomic(intent) or current_depth >= self.max_depth:
            subgoal = SubGoal(
                subgoal_id="sg_leaf_0",
                description=f"Execute operational objective: {intent}",
                is_atomic=True,
                precondition="Navigate to the relevant domain context or view.",
                postcondition="Directly verify target observation satisfies query constraints and extract output.",
                invariants=["Verify target entity criteria match before reporting output."],
                depth=current_depth,
            )
            plan = HierarchicalExecutionPlan(
                task_intent=intent,
                plan_type="direct_atomic",
                subgoals=[subgoal],
                milestones=[f"Milestone 1: {subgoal.description}"],
                checkpoint_invariants=[
                    "Verify target entity matches user constraints before emitting answer.",
                ],
                injected_prompt_text="",  # Standard atomic execution needs no overhead
            )
            self._plan_cache[cache_key] = plan
            return plan

        # Case 2: Matching Macro-Routine in Memory (2-Step Macro Plan: [Learned Macro] + [Delta])
        matching_mem, sim, deltas = self.find_matching_macro_schema(intent, memories)
        if matching_mem is not None:
            mem_title = getattr(matching_mem, "title", "Learned Macro-Routine")
            mem_proc = getattr(matching_mem, "procedure", "Execute validated navigational and aggregation workflow.")
            mem_id = getattr(matching_mem, "memory_id", "mem_prior")

            delta_str = "; ".join(f"{k}: {v}" for k, v in deltas.items()) if deltas else "Adapt specific filter parameters to current intent"

            sg1 = SubGoal(
                subgoal_id="sg_macro_routine",
                description=f"Execute Learned Macro-Routine from [{mem_title}]: {mem_proc}",
                is_atomic=False,
                bound_memory_id=mem_id,
                bound_memory_title=mem_title,
                precondition=f"Access domain view verified by memory {mem_id}.",
                postcondition="Complete baseline navigational and aggregation pipeline.",
                invariants=["Follow validated workflow structure without deviating into unverified views."],
                depth=current_depth,
            )
            sg2 = SubGoal(
                subgoal_id="sg_macro_delta",
                description=f"Apply Target Adaptation (Delta): {delta_str}",
                is_atomic=True,
                precondition="Baseline macro aggregation data is visible in observation.",
                postcondition=f"Select target record satisfying exact delta condition ({delta_str}).",
                invariants=[f"Strictly enforce divergent condition ({delta_str}); do NOT output default memory winner."],
                recovery_route="If delta criteria are not met, re-filter records by target parameter.",
                depth=current_depth,
            )

            intent_lower = intent.lower()
            is_extremum = any(w in intent_lower for w in ("most", "oldest", "newest", "latest", "earliest", "highest", "lowest", "first", "last", "rank", "top"))

            prompt_lines = [
                "# Memory Item: [Observed Successful Routine]",
                f"## Intent: {intent}",
                f"## Validated Routine: {mem_proc}",
                f"## Target Adaptation: {'Strictly enforce target condition ' if include_contract_guidance else ''}({delta_str}).",
            ]
            if include_contract_guidance:
                prompt_lines.extend([
                    "## Verification Invariants:",
                    "- [COMPLETE CONSTRAINT VERIFICATION]: An observation may only be used to satisfy a goal if ALL specified constraints (criteria, state, metric scope) are explicitly verified in the active view.",
                    "- Verify extracted entity strictly matches user constraints before submitting.",
                    "- [SEARCH/FILTER EFFECTIVENESS INVARIANT]: When an interaction, search, or filter yields '0 records found' or an empty table, do not immediately conclude that the target entity does not exist; verify whether alternative query/search formulations or input representations exist before concluding.",
                ])
                if is_extremum:
                    prompt_lines.append(
                        "- [ORDERED SELECTION INVARIANT]: When selecting an extremum or ranked element, verify that candidates are explicitly ordered by the target metric, or examine all candidates in the scoped set before selecting. Never assume an unsorted default view satisfies the extremum condition."
                    )

            plan = HierarchicalExecutionPlan(
                task_intent=intent,
                plan_type="macro_two_step",
                subgoals=[sg1, sg2],
                milestones=[
                    f"Milestone 1 (Macro): {sg1.description}",
                    f"Milestone 2 (Delta): {sg2.description}",
                ],
                checkpoint_invariants=[
                    f"Enforce delta constraint ({delta_str})",
                    "Verify extracted values match observation before submitting.",
                ],
                injected_prompt_text="\n".join(prompt_lines),
            )
            self._plan_cache[cache_key] = plan
            return plan

        # Case 3: Recursive Divide-and-Conquer Fallback (Cold Memory / Unlearned Compound Task)
        # Factor the unlearned compound task into atomic sub-goals and perform Subtask-Level Memory Binding
        llm_subgoals = self._factorize_via_llm(
            intent, benchmark_context,
            include_contract_guidance=include_contract_guidance,
        )

        subgoals: list[SubGoal] = []
        milestones: list[str] = []
        checkpoint_invariants: list[str] = []

        if llm_subgoals:
            for idx, raw_sg in enumerate(llm_subgoals, 1):
                desc = raw_sg.get("description", f"Sub-goal {idx}")
                is_sub_atomic = raw_sg.get("is_atomic", True)
                pre = raw_sg.get("precondition", "Target context active.")
                post = raw_sg.get("postcondition", "Sub-goal objective observed.")
                invs = raw_sg.get("invariants", ["Verify observation state matches requirements."])
                rec = raw_sg.get("recovery_route", "Inspect related controls or refresh view.")

                # If a sub-goal is still compound and we haven't exceeded depth, recurse
                child_subgoals: list[SubGoal] = []
                if not is_sub_atomic and current_depth + 1 < self.max_depth:
                    child_plan = self.decompose(
                        intent=desc,
                        memories=memories,
                        benchmark_context=benchmark_context,
                        current_depth=current_depth + 1,
                        include_contract_guidance=include_contract_guidance,
                    )
                    child_subgoals = child_plan.subgoals

                sg = SubGoal(
                    subgoal_id=f"sg_rec_{current_depth}_{idx}",
                    description=desc,
                    is_atomic=is_sub_atomic or len(child_subgoals) == 0,
                    precondition=pre,
                    postcondition=post,
                    invariants=invs if isinstance(invs, list) else [str(invs)],
                    recovery_route=rec,
                    children=child_subgoals,
                    depth=current_depth,
                )
                subgoals.append(sg)
                milestones.append(f"Milestone {idx}: {desc}")
                checkpoint_invariants.append(f"Milestone {idx} Verification: {post}")
        else:
            # Domain-agnostic algorithmic fallback based on Constraint Composition Pipeline
            subgoals = self._algorithmic_fallback_factorization(intent, current_depth)
            for idx, sg in enumerate(subgoals, 1):
                milestones.append(f"Milestone {idx}: {sg.description}")
                checkpoint_invariants.append(f"Milestone {idx} Verification: {sg.postcondition}")

        # Subtask-Level Memory Binding
        for sg in subgoals:
            bound_mem, mem_sim = self._find_matching_subtask_memory(sg.description, memories, task_intent=intent)
            if bound_mem is not None:
                sg.bound_memory_id = getattr(bound_mem, "memory_id", "mem_bound")
                sg.bound_memory_title = getattr(bound_mem, "title", "Prior Procedural Memory")
                sg.bound_memory_proc = getattr(bound_mem, "procedure", "")

        # Construct milestone prompt guidance with explicit subtask memory boundaries
        prompt_lines = [
            "# Hierarchical Execution Plan [Mode: Recursive Divide-and-Conquer]",
            f"## Compound Task Intent: {intent}",
            "## Strategy: Multi-stage constraint composition broken down into sequential state milestones.",
            "",
            "### Sequential Milestones to Achieve:",
        ]

        total_milestones = len(subgoals)
        for idx, sg in enumerate(subgoals, 1):
            bound_title = getattr(sg, "bound_memory_title", None)
            bound_proc = getattr(sg, "bound_memory_proc", None)

            if bound_title and bound_proc:
                prompt_lines.extend([
                    f"**Milestone {idx} [Supported by Prior Memory: {bound_title}]**: {sg.description}",
                    f"- *Validated Routine*: {bound_proc}",
                    f"- *Subtask Scope*: This memory routine applies strictly to achieving Milestone {idx}. Subsequent milestones require independent execution.",
                ])
            else:
                prompt_lines.extend([
                    f"**Milestone {idx} [Novel Subtask - Independent Execution]**: {sg.description}",
                ])

            # Check if subgoal requires extremum / ordering verification
            desc_lower = sg.description.lower()
            if include_contract_guidance and any(w in desc_lower for w in ("most", "oldest", "newest", "latest", "earliest", "highest", "lowest", "first", "last", "rank", "top")):
                prompt_lines.append(
                    "- *Cognitive Invariant*: [ORDERED SELECTION INVARIANT] When selecting an extremum or ranked element, verify that candidates are explicitly ordered by the target metric, or examine all candidates in the scoped set before selecting. Never assume an unsorted default view satisfies the extremum condition."
                )
            elif include_contract_guidance:
                inv_text = sg.invariants[0] if sg.invariants else "Verify state before proceeding"
                prompt_lines.append(f"- *Invariant*: {inv_text}")

            if sg.children:
                for c_idx, ch in enumerate(sg.children, 1):
                    prompt_lines.append(f"  - *Sub-step {idx}.{c_idx}*: {ch.description}")
            prompt_lines.append("")

        if include_contract_guidance:
            prompt_lines.extend([
                "### Mandatory Execution Invariants:",
                f"- **[NON-PREMATURE TERMINATION INVARIANT]**: Milestones 1 to {max(1, total_milestones - 1)} are internal state checkpoints. You must NOT emit final output or terminate the task until ALL preceding milestones have been verified in sequence.",
                "- **[COMPLETE CONSTRAINT VERIFICATION]**: An observation may only be used to satisfy a goal or milestone if ALL specified constraints (criteria, state, metric scope) are explicitly verified in the active observation. If any constraint is unverified or ambiguous, you MUST actively perform the necessary scoping operations to prove it before concluding.",
                "- **[CHECKPOINT DISCIPLINE]**: Execute each milestone sequentially to establish prerequisites before moving to the next.",
                "- **[FINAL VERIFICATION]**: Before submitting your answer, verify that all extracted values strictly satisfy all query constraints.",
                "- **[ACTIVE VIEW PRECEDENCE]**: If the target data, metric, or ranking table is already present and visible in the current view (e.g. dashboard summary or active panel), extract it directly from the current view instead of navigating away.",
                "- **[SEARCH/FILTER EFFECTIVENESS INVARIANT]**: When an interaction, search, or filter yields '0 records found' or an empty table, do not immediately conclude that the target entity does not exist; verify whether alternative query/search formulations or input representations exist before concluding.",
                "- **[ORDERED COLUMN VERIFICATION]**: When extracting the top/ranked item from a table, ensure the table is explicitly sorted by the target metric column (e.g. click the metric column header to sort descending if needed). Never pick the highest value from an arbitrary unsorted or paginated subset.",
                "- **[CONCISE VALUE FORMATTING]**: When submitting your final answer to the user, output strictly the exact target value, number, or entity name without conversational filler or full sentence explanations (e.g. send_msg_to_user('value') rather than send_msg_to_user('The value is value')).",
            ])

        plan = HierarchicalExecutionPlan(
            task_intent=intent,
            plan_type="recursive_atomic",
            subgoals=subgoals,
            milestones=milestones,
            checkpoint_invariants=checkpoint_invariants + ["Verify extracted values match observation before submitting."],
            injected_prompt_text="\n".join(prompt_lines).strip(),
        )
        self._plan_cache[cache_key] = plan
        return plan

    def _factorize_via_llm(
        self,
        intent: str,
        benchmark_context: str = "",
        include_contract_guidance: bool = False,
    ) -> list[dict[str, Any]]:
        """Call LLM to factorize compound intents into atomic sub-goals using native environment context."""
        if not self.api_key:
            return []

        context_block = f"Operating Environment Context:\n{benchmark_context}\n\n" if benchmark_context else ""
        if include_contract_guidance:
            system_prompt = (
                "You are a Task Decomposer.\n"
                f"{context_block}"
                "Given a complex user intent, factorize it into 2 to 3 sequential operational milestones following the Constraint Composition Principle:\n"
                "- Stage 1: Scope & Prerequisite Condition Restriction\n"
                "- Stage 2: Candidate Selection / Extremum Ordering\n"
                "- Stage 3: Target Attribute Projection & Constraint Verification\n\n"
                "Milestones must represent observable intermediate state checkpoints in the environment. Intermediate milestones must never emit final output.\n"
                "Each sub-goal must specify:\n"
                "- 'description': clear operational action describing the state milestone\n"
                "- 'is_atomic': boolean (true if single action/read, false if compound)\n"
                "- 'precondition': environmental state required before executing\n"
                "- 'postcondition': verifiable state or data observed after executing\n"
                "- 'invariants': list of safety or correctness checks\n"
                "- 'recovery_route': alternative action if postcondition fails\n"
                "Return strictly valid JSON with key 'subgoals': [ ... ]."
            )
            user_prompt = (
                f"User Intent: \"{intent}\"\n\n"
                "Decompose this complex task into an ordered sequence of atomic operational milestones following Constraint Composition.\n"
                "The final milestone must be verifying all collected data against query constraints before formatting output."
            )
        else:
            system_prompt = (
                "You are a Task Decomposer.\n"
                f"{context_block}"
                "Break the complex intent into 2 to 3 ordered, actionable milestones.\n"
                "Each milestone should have a short description and an is_atomic boolean. "
                "Return strictly valid JSON with key 'subgoals': [ ... ]."
            )
            user_prompt = f"User Intent: \"{intent}\"\n\nList the operational milestones in order."

        resp_dict = _call_openrouter_json(
            api_key=self.api_key,
            model=self.model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=600,
            temperature=0.0,
            usage_sink=self._record_usage,
        )

        if resp_dict and "subgoals" in resp_dict and isinstance(resp_dict["subgoals"], list):
            return resp_dict["subgoals"]

        return []

    def _algorithmic_fallback_factorization(self, intent: str, depth: int) -> list[SubGoal]:
        """Algorithmic domain-agnostic 3-phase factorization following Constraint Composition."""
        sg1 = SubGoal(
            subgoal_id=f"sg_fb_{depth}_1",
            description="Phase 1: Context & Condition Scoping - Locate candidate domain context and apply prerequisite state filters",
            is_atomic=True,
            precondition="Access environment state and identify controls to isolate target scope.",
            postcondition="Target scoped collection or state is isolated.",
            invariants=["Do not proceed until prerequisite scoping condition is active."],
            recovery_route="Check navigation menus, search bars, or state filters.",
            depth=depth,
        )
        sg2 = SubGoal(
            subgoal_id=f"sg_fb_{depth}_2",
            description="Phase 2: Candidate Ordering & Selection - Order candidates by target metric/extremum and identify qualifying entity",
            is_atomic=False,
            precondition="Scoped collection is active.",
            postcondition="Target candidate entity satisfying extremum or ordering criterion is isolated.",
            invariants=["[ORDERED SELECTION INVARIANT] Verify that candidates are explicitly ordered by the target metric before selecting."],
            recovery_route="Verify candidate ordering or inspect all entries in the scoped set.",
            depth=depth,
        )
        sg3 = SubGoal(
            subgoal_id=f"sg_fb_{depth}_3",
            description="Phase 3: Attribute Projection & Verification - Verify all query constraints match before projecting requested output",
            is_atomic=True,
            precondition="Candidate entity is selected and isolated.",
            postcondition="Target entity attribute value extracted and verified against all query constraints.",
            invariants=["Verify all constraints are satisfied before final response."],
            recovery_route="Re-verify candidate attributes against user query constraints.",
            depth=depth,
        )
        return [sg1, sg2, sg3]
