"""Append-only successor budget ledger with immutable carried-forward exposure."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from .checkpoints import RunStore
from .providers import BudgetExceeded


class SuccessorLedger:
    def __init__(self, store: RunStore, *, parent_root: Path, max_usd: float = 1.0, max_attempts: int = 88):
        if max_usd != 1.0 or max_attempts != 88:
            raise ValueError("successor is pinned to USD 1 and 88 total attempts")
        self.store, self.parent_root = store, parent_root
        reservations = sorted((parent_root / "reservations").glob("*.json"))
        settlements = {p.stem: json.loads(p.read_text())["actual_usd"] for p in (parent_root / "settlements").glob("*.json")}
        self.inherited = {
            p.stem: {"reserved_usd": json.loads(p.read_text())["reserved_usd"], "actual_usd": settlements.get(p.stem)}
            for p in reservations
        }
        if len(self.inherited) != 10:
            raise ValueError("expected exactly 10 immutable parent attempt records")
        exposure = sum(item["actual_usd"] if item["actual_usd"] is not None else item["reserved_usd"] for item in self.inherited.values())
        if abs(exposure - 0.03131748) > 1e-12:
            raise ValueError("parent exposure does not match authorized carry-forward")
        manifest = {
            "parent_root": str(parent_root),
            "parent_records": [
                {"id": p.stem, "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                 "settlement_sha256": hashlib.sha256((parent_root / "settlements" / f"{p.stem}.json").read_bytes()).hexdigest() if (parent_root / "settlements" / f"{p.stem}.json").exists() else None}
                for p in reservations
            ],
            "inherited_attempts": 10, "inherited_exposure_usd": exposure,
            "max_attempts": 88, "max_usd": 1.0,
        }
        store.write("successor", "carry_forward_manifest", manifest)
        self.local_reservations: dict[str, float] = {}
        self.local_settlements: dict[str, float] = {}
        if store.root:
            for p in (store.root / "reservations").glob("*.json"):
                self.local_reservations[p.stem] = json.loads(p.read_text())["reserved_usd"]
            for p in (store.root / "settlements").glob("*.json"):
                self.local_settlements[p.stem] = json.loads(p.read_text())["actual_usd"]

    @property
    def charged_or_reserved(self) -> float:
        return 0.03131748 + sum(self.local_settlements.get(k, v) for k, v in self.local_reservations.items())

    @property
    def attempts_used(self) -> int:
        return 10 + len(self.local_reservations)

    def reserve(self, key: str, upper_usd: float, metadata: dict) -> None:
        if not math.isfinite(upper_usd) or upper_usd < 0 or self.attempts_used >= 88:
            raise BudgetExceeded("successor attempt ceiling reached")
        if self.charged_or_reserved + upper_usd > 1.0:
            raise BudgetExceeded("successor USD ceiling reached")
        self.store.write("reservations", key, {"reserved_usd": upper_usd, **metadata})
        self.local_reservations[key] = upper_usd

    def settle(self, key: str, actual_usd: float) -> None:
        if not math.isfinite(actual_usd) or actual_usd < 0 or actual_usd > self.local_reservations[key] + 1e-12:
            raise BudgetExceeded("invalid or over-budget settlement")
        self.store.write("settlements", key, {"actual_usd": actual_usd})
        self.local_settlements[key] = actual_usd
