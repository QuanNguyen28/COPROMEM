"""Contract-bank retrieval, admission, budget enforcement, and persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contracts import Contract, validate_contract
from .types import (
    AdmissionDecision,
    EpisodicTrace,
    HandoffEvent,
    ReplayEvidence,
    ScopeEvidence,
    CreditAssignmentResult,
    FailureTier,
    VerificationResult,
    as_jsonable,
)


@dataclass(frozen=True)
class Budgets:
    storage_tokens: int = 1_000
    read_tokens: int = 180
    verification_cost: float = 2.0


@dataclass
class ContractBank:
    contracts: list[Contract] = field(default_factory=list)
    budgets: Budgets = field(default_factory=Budgets)

    def retrieve(self, event: HandoffEvent) -> list[Contract]:
        """Return the smallest eligible set within runtime budgets.

        Rank by observed conditional benefit, then prefer lower verifier cost and
        smaller contracts. Counterexamples are enforced by ``is_eligible`` before
        ranking, giving veto conditions priority over lexical resemblance.
        """

        candidates = [
            item
            for item in self.contracts
            if item.status == "admitted"
            and item.interface == event.interface
            and item.is_eligible(event)
        ]
        candidates.sort(
            key=lambda item: (
                -float(item.evidence.get("conditional_benefit", 0.0)),
                item.estimated_read_tokens,
                item.contract_id,
            )
        )
        picked: list[Contract] = []
        used_tokens = 0
        used_cost = 0.0
        for contract in candidates:
            if used_tokens + contract.estimated_read_tokens > self.budgets.read_tokens:
                continue
            if used_cost + 0.05 > self.budgets.verification_cost:
                continue
            picked.append(contract)
            used_tokens += contract.estimated_read_tokens
            used_cost += 0.05
        return picked

    def admission_decision(
        self,
        replay: ReplayEvidence,
        scope: ScopeEvidence,
        min_gain: float = 0.05,
        harm_cap: int = 0,
        min_transfer: float = 0.50,
    ) -> AdmissionDecision:
        reasons: list[str] = []
        if replay.net_gain_over_text < min_gain:
            reasons.append("replay gain over textual rule is below threshold")
        if replay.harmful_flips > harm_cap:
            reasons.append("replay harmful-flip cap exceeded")
        if scope.boundary_harmful_flips > harm_cap:
            reasons.append("boundary harmful-flip cap exceeded")
        if scope.transfer_success < min_transfer:
            reasons.append("transfer success is below threshold")
        if scope.veto_accuracy < 0.95:
            reasons.append("counterexample veto is not reliable")
        return AdmissionDecision(
            not reasons, tuple(reasons or ["passed replay, transfer, and harm gates"])
        )

    def admit(
        self, contract: Contract, replay: ReplayEvidence, scope: ScopeEvidence
    ) -> AdmissionDecision:
        validate_contract(contract)
        decision = self.admission_decision(replay, scope)
        if not decision.admitted:
            return decision
        enriched = contract.with_evidence(
            replay=as_jsonable(replay),
            scope=as_jsonable(scope),
            conditional_benefit=replay.net_gain_over_text,
            verifier_cost=replay.verifier_cost,
        ).admitted()
        self.contracts = [
            item for item in self.contracts if item.contract_id != enriched.contract_id
        ]
        self.contracts.append(enriched)
        self.enforce_budgets()
        return decision

    def enforce_budgets(self) -> None:
        ranked = sorted(
            self.contracts,
            key=lambda item: (
                float(item.evidence.get("conditional_benefit", 0.0)),
                -item.storage_tokens,
                item.contract_id,
            ),
            reverse=True,
        )
        kept: list[Contract] = []
        used = 0
        for contract in ranked:
            if used + contract.storage_tokens <= self.budgets.storage_tokens:
                kept.append(contract)
                used += contract.storage_tokens
        self.contracts = sorted(kept, key=lambda item: item.contract_id)

    def save(self, path: str | Path) -> None:
        payload = {
            "budgets": as_jsonable(self.budgets),
            "contracts": [as_jsonable(item) for item in self.contracts],
        }
        Path(path).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    @classmethod
    def load(cls, path: str | Path) -> ContractBank:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        bank = cls(budgets=Budgets(**payload["budgets"]))
        for raw in payload["contracts"]:
            raw["counterexamples"] = tuple(raw["counterexamples"])
            raw["required_fields"] = tuple(raw["required_fields"])
            bank.contracts.append(Contract(**raw))
        return bank


@dataclass
class FastEpisodicBuffer:
    """Fast episodic store for raw execution traces with Mattar-Daw prioritized replay."""

    traces: list[EpisodicTrace] = field(default_factory=list)
    max_capacity: int = 200

    def add_trace(
        self,
        trace: EpisodicTrace,
        task_frequency: float = 1.0,
    ) -> EpisodicTrace:
        priority = self.calculate_priority(trace, task_frequency=task_frequency)
        enriched = EpisodicTrace(
            trace_id=trace.trace_id,
            task_id=trace.task_id,
            task_state=trace.task_state,
            schema_id=trace.schema_id,
            handoff_events=trace.handoff_events,
            success=trace.success,
            credit_result=trace.credit_result,
            surprise=trace.surprise,
            uncertainty=trace.uncertainty,
            replay_priority=priority,
        )
        self.traces.append(enriched)
        if len(self.traces) > self.max_capacity:
            # Drop lowest priority trace
            self.traces.sort(key=lambda t: t.replay_priority)
            self.traces.pop(0)
        return enriched

    @staticmethod
    def calculate_priority(trace: EpisodicTrace, task_frequency: float = 1.0) -> float:
        need = max(0.1, task_frequency)
        # A verified, localized failure is more actionable than an unexplained
        # outcome. This is a repairability proxy, not an observed causal gain.
        gain = (
            1.0 if not trace.success and trace.credit_result is not None
            and trace.credit_result.tier is not FailureTier.UNKNOWN
            else 0.25
        )
        surprise_term = 1.0 + max(0.0, trace.surprise)
        uncertainty_term = 1.0 + max(0.0, trace.uncertainty)
        return float(need * gain * surprise_term * uncertainty_term)

    def sample_prioritized(self, batch_size: int = 10) -> list[EpisodicTrace]:
        sorted_traces = sorted(self.traces, key=lambda t: t.replay_priority, reverse=True)
        return sorted_traces[:batch_size]


@dataclass
class StructuralSchemaBank:
    """Slow consolidated procedural memory bank for DecompositionSchemas with Anti-Lock-in."""

    schemas: list[DecompositionSchema] = field(default_factory=list)
    fast_buffer: FastEpisodicBuffer = field(default_factory=FastEpisodicBuffer)
    consolidated_trace_ids: set[str] = field(default_factory=set)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schemas": [schema.as_dict() for schema in self.schemas],
            "traces": [as_jsonable(trace) for trace in self.fast_buffer.traces],
            "max_capacity": self.fast_buffer.max_capacity,
            "consolidated_trace_ids": sorted(self.consolidated_trace_ids),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> StructuralSchemaBank:
        from .schema import DecompositionSchema

        bank = cls(
            schemas=[DecompositionSchema.from_dict(item) for item in raw.get("schemas", ())],
            fast_buffer=FastEpisodicBuffer(max_capacity=int(raw.get("max_capacity", 200))),
            consolidated_trace_ids=set(raw.get("consolidated_trace_ids", ())),
        )
        for item in raw.get("traces", ()):
            credit = item.get("credit_result")
            if credit is not None:
                credit = CreditAssignmentResult(
                    **{**credit, "tier": FailureTier(credit["tier"])}
                )
            handoffs = tuple(
                HandoffEvent(
                    **{**event, "verifier_results": tuple(
                        VerificationResult(**result)
                        for result in event.get("verifier_results", ())
                    )}
                )
                for event in item.get("handoff_events", ())
            )
            bank.fast_buffer.traces.append(EpisodicTrace(
                **{**item, "handoff_events": handoffs, "credit_result": credit}
            ))
        return bank

    def admit_schema(self, schema: DecompositionSchema) -> None:
        admitted = schema.admitted()
        self.schemas = [s for s in self.schemas if s.schema_id != admitted.schema_id]
        self.schemas.append(admitted)

    def retrieve_with_anti_lockin(
        self,
        task_cues: tuple[str, ...],
        task_state: dict[str, Any],
        semantic_threshold: float = 0.35,
        exploration_uncertainty: float = 0.70,
        task_schema: DecompositionSchema | None = None,
    ) -> tuple[DecompositionSchema | None, DecompositionSchema | None, bool]:
        """Retrieve primary exploit schema and diverse alternative schema (Anti-Lock-in).

        Returns:
            (exploit_schema, diverse_alternative_schema, should_explore)
        """
        from .pattern_separation import PatternSeparationEngine

        engine = PatternSeparationEngine(semantic_threshold=semantic_threshold)
        candidates: list[tuple[float, DecompositionSchema]] = []

        for schema in self.schemas:
            if schema.status != "admitted":
                continue
            if task_state.get("domain") and schema.task_family != f"Domain_{task_state['domain']}":
                continue
            decision = engine.evaluate(
                task_cues, task_state, schema,
                candidate_state={
                    "constraints": schema.structural_stats.get("constraints", {}),
                    "intent": schema.structural_stats.get("source_intent"),
                },
                task_schema=task_schema,
            )
            if not decision.should_separate and decision.semantic_similarity >= semantic_threshold:
                # Rank by semantic similarity + historical reliability
                reliability = schema.transfer_reliability
                score = 0.6 * decision.semantic_similarity + 0.4 * reliability
                candidates.append((score, schema))

        candidates.sort(key=lambda x: x[0], reverse=True)

        if not candidates:
            return None, None, True

        exploit_schema = candidates[0][1]

        # Find diverse alternative schema with different edge structure
        diverse_alternative: DecompositionSchema | None = None
        from .pattern_separation import calculate_graph_distance

        for _, alt in candidates[1:]:
            if calculate_graph_distance(exploit_schema, alt) > 0.20:
                diverse_alternative = alt
                break

        # Anti-lock-in exploration branch if uncertainty is high or single strategy monopoly
        should_explore = (
            diverse_alternative is None
            or exploit_schema.transfer_reliability < exploration_uncertainty
        )

        return exploit_schema, diverse_alternative, should_explore

    def consolidate_offline(self, min_priority: float = 0.40) -> int:
        """Consolidate high-priority episodic traces into persistent schema reliability stats."""
        top_traces = [
            t for t in self.fast_buffer.sample_prioritized(self.fast_buffer.max_capacity)
            if t.replay_priority >= min_priority
            and t.trace_id not in self.consolidated_trace_ids
        ]
        consolidated_count = 0

        schema_map = {s.schema_id: s for s in self.schemas}
        for trace in top_traces:
            if not trace.schema_id or trace.schema_id not in schema_map:
                continue
            schema = schema_map[trace.schema_id]
            exec_count = schema.execution_count + 1
            curr_rel = schema.transfer_reliability
            # Update moving average of transfer reliability
            delta = (1.0 if trace.success else 0.0) - curr_rel
            new_rel = max(0.0, min(1.0, curr_rel + delta / exec_count))

            updated = schema.with_stats(
                execution_count=exec_count,
                transfer_reliability=round(new_rel, 3),
                success_count=int(schema.structural_stats.get("success_count", 0)) + int(trace.success),
            )
            if (
                updated.status == "candidate"
                and updated.structural_stats["success_count"] >= 2
                and updated.transfer_reliability >= 0.7
            ):
                updated = updated.admitted()
            schema_map[trace.schema_id] = updated
            self.consolidated_trace_ids.add(trace.trace_id)
            consolidated_count += 1

        self.schemas = list(schema_map.values())
        return consolidated_count
