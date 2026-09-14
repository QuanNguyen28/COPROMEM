"""Contract-bank retrieval, admission, budget enforcement, and persistence."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from .contracts import Contract, validate_contract
from .types import AdmissionDecision, HandoffEvent, ReplayEvidence, ScopeEvidence, as_jsonable


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
            if item.status == "admitted" and item.interface == event.interface and item.is_eligible(event)
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
        return AdmissionDecision(not reasons, tuple(reasons or ["passed replay, transfer, and harm gates"]))

    def admit(self, contract: Contract, replay: ReplayEvidence, scope: ScopeEvidence) -> AdmissionDecision:
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
        self.contracts = [item for item in self.contracts if item.contract_id != enriched.contract_id]
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
        payload = {"budgets": as_jsonable(self.budgets), "contracts": [as_jsonable(item) for item in self.contracts]}
        Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "ContractBank":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        bank = cls(budgets=Budgets(**payload["budgets"]))
        for raw in payload["contracts"]:
            raw["counterexamples"] = tuple(raw["counterexamples"])
            raw["required_fields"] = tuple(raw["required_fields"])
            bank.contracts.append(Contract(**raw))
        return bank
