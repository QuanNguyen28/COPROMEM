"""Append-only corrected-smoke ledger carrying every prior attempt forward."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Iterable

from .checkpoints import RunStore
from .providers import BudgetExceeded


class CorrectedSmokeLedger:
    """USD-1 ledger whose historical records are immutable input, not mutable state."""

    def __init__(self, store: RunStore, *, historical_roots: Iterable[Path], max_new_attempts: int = 60,
                 expected_historical_attempts: int = 56, expected_historical_exposure: float = 0.06416778,
                 max_usd: float = 1.0) -> None:
        self.store = store
        self.max_new_attempts = max_new_attempts
        self.max_usd = max_usd
        self.inherited: dict[str, float] = {}
        records = []
        for root in historical_roots:
            root = Path(root)
            settlements = {p.stem: json.loads(p.read_text())["actual_usd"] for p in (root / "settlements").glob("*.json")}
            for reservation in sorted((root / "reservations").glob("*.json")):
                data = json.loads(reservation.read_text())
                identity = f"{root.name}:{reservation.stem}"
                amount = settlements.get(reservation.stem, data["reserved_usd"])
                self.inherited[identity] = amount
                records.append({"id": identity, "reservation_sha256": hashlib.sha256(reservation.read_bytes()).hexdigest(),
                                "settlement_sha256": hashlib.sha256((root / "settlements" / f"{reservation.stem}.json").read_bytes()).hexdigest() if reservation.stem in settlements else None,
                                "exposure_usd": amount})
        if len(records) != expected_historical_attempts:
            raise ValueError(f"expected {expected_historical_attempts} carried records, found {len(records)}")
        exposure = sum(self.inherited.values())
        if abs(exposure - expected_historical_exposure) > 1e-10:
            raise ValueError(f"historical exposure mismatch: {exposure}")
        self.store.write("corrected_successor", "carry_forward_manifest", {
            "historical_records": records, "historical_attempts": len(records),
            "historical_exposure_usd": exposure, "max_usd": max_usd,
            "max_new_attempts": max_new_attempts,
        })
        self.local_reservations: dict[str, float] = {}
        self.local_settlements: dict[str, float] = {}
        if store.root:
            for path in (store.root / "reservations").glob("*.json"):
                self.local_reservations[path.stem] = json.loads(path.read_text())["reserved_usd"]
            for path in (store.root / "settlements").glob("*.json"):
                self.local_settlements[path.stem] = json.loads(path.read_text())["actual_usd"]

    @property
    def charged_or_reserved(self) -> float:
        return sum(self.inherited.values()) + sum(self.local_settlements.get(k, v) for k, v in self.local_reservations.items())

    @property
    def attempts_used(self) -> int:
        return len(self.inherited) + len(self.local_reservations)

    def reserve(self, key: str, upper_usd: float, metadata: dict) -> None:
        if not math.isfinite(upper_usd) or upper_usd <= 0:
            raise BudgetExceeded("invalid corrected-smoke reservation")
        if len(self.local_reservations) >= self.max_new_attempts:
            raise BudgetExceeded("corrected-smoke attempt ceiling reached")
        if self.charged_or_reserved + upper_usd > self.max_usd:
            raise BudgetExceeded("corrected-smoke USD ceiling reached")
        self.store.write("reservations", key, {"reserved_usd": upper_usd, **metadata})
        self.local_reservations[key] = upper_usd

    def settle(self, key: str, actual_usd: float) -> None:
        if not math.isfinite(actual_usd) or actual_usd < 0 or actual_usd > self.local_reservations[key] + 1e-12:
            raise BudgetExceeded("invalid corrected-smoke settlement")
        self.store.write("settlements", key, {"actual_usd": actual_usd})
        self.local_settlements[key] = actual_usd
