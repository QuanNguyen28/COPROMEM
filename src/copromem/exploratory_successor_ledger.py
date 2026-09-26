"""Append-only ledger for the post-gate, failure-informed exploratory pilot.

This is intentionally separate from the confirmatory successor ledger.  It
imports immutable historical reservations as evidence, while bounding only the
new exploratory dispatch envelope.  Settling a cheap call never makes another
unregistered call affordable: both the new-attempt and cumulative-reservation
ceilings are monotone.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Iterable

from .checkpoints import RunStore
from .providers import BudgetExceeded


class ExploratorySuccessorLedger:
    def __init__(
        self,
        store: RunStore,
        *,
        historical_roots: Iterable[Path],
        expected_historical_attempts: int,
        expected_historical_exposure: float,
        max_new_attempts: int,
        max_new_reserved_usd: float,
        max_usd: float = 35.0,
    ) -> None:
        self.store = store
        self.max_new_attempts = max_new_attempts
        self.max_new_reserved_usd = max_new_reserved_usd
        self.max_usd = max_usd
        self.inherited: dict[str, float] = {}
        records: list[dict[str, object]] = []
        for root in map(Path, historical_roots):
            reservations = root / "reservations"
            settlements = root / "settlements"
            if not reservations.is_dir():
                raise ValueError(f"historical ledger missing reservations: {root}")
            settled = {
                path.stem: float(json.loads(path.read_text(encoding="utf-8"))["actual_usd"])
                for path in settlements.glob("*.json")
            } if settlements.is_dir() else {}
            for reservation in sorted(reservations.glob("*.json")):
                data = json.loads(reservation.read_text(encoding="utf-8"))
                identity = f"{root.name}:{reservation.stem}"
                if identity in self.inherited:
                    raise ValueError(f"duplicate inherited ledger identity: {identity}")
                exposure = settled.get(reservation.stem, float(data["reserved_usd"]))
                self.inherited[identity] = exposure
                records.append({
                    "id": identity,
                    "reservation_sha256": hashlib.sha256(reservation.read_bytes()).hexdigest(),
                    "settlement_sha256": hashlib.sha256((settlements / f"{reservation.stem}.json").read_bytes()).hexdigest()
                    if reservation.stem in settled else None,
                    "charged_or_reserved_usd": exposure,
                })
        if len(records) != expected_historical_attempts:
            raise ValueError(f"historical attempt mismatch: {len(records)}")
        historical = sum(self.inherited.values())
        if abs(historical - expected_historical_exposure) > 1e-10:
            raise ValueError(f"historical exposure mismatch: {historical}")
        if historical + max_new_reserved_usd > max_usd:
            raise ValueError("registered exploratory envelope exceeds hard cap")
        self.store.write("exploratory_successor", "carry_forward_manifest", {
            "historical_records": records,
            "historical_attempts": len(records),
            "historical_exposure_usd": historical,
            "max_new_attempts": max_new_attempts,
            "max_new_reserved_usd": max_new_reserved_usd,
            "max_usd": max_usd,
        })
        self.local_reservations: dict[str, float] = {}
        self.local_settlements: dict[str, float] = {}
        for path in (store.root / "reservations").glob("*.json") if store.root else ():
            self.local_reservations[path.stem] = float(json.loads(path.read_text(encoding="utf-8"))["reserved_usd"])
        for path in (store.root / "settlements").glob("*.json") if store.root else ():
            self.local_settlements[path.stem] = float(json.loads(path.read_text(encoding="utf-8"))["actual_usd"])

    @property
    def attempts_used(self) -> int:
        return len(self.inherited) + len(self.local_reservations)

    @property
    def charged_or_reserved(self) -> float:
        return sum(self.inherited.values()) + sum(self.local_settlements.get(key, amount) for key, amount in self.local_reservations.items())

    @property
    def reserved_new_total(self) -> float:
        return sum(self.local_reservations.values())

    def reserve(self, key: str, upper_usd: float, metadata: dict) -> None:
        if key in self.local_reservations:
            raise BudgetExceeded("duplicate exploratory reservation")
        if not math.isfinite(upper_usd) or upper_usd <= 0:
            raise BudgetExceeded("invalid exploratory reservation")
        if len(self.local_reservations) >= self.max_new_attempts:
            raise BudgetExceeded("exploratory attempt ceiling reached")
        if self.reserved_new_total + upper_usd > self.max_new_reserved_usd + 1e-12:
            raise BudgetExceeded("exploratory registered envelope reached")
        if self.charged_or_reserved + upper_usd > self.max_usd + 1e-12:
            raise BudgetExceeded("exploratory USD ceiling reached")
        self.store.write("reservations", key, {"reserved_usd": upper_usd, **metadata})
        self.local_reservations[key] = upper_usd

    def settle(self, key: str, actual_usd: float) -> None:
        if key not in self.local_reservations:
            raise BudgetExceeded("unknown exploratory settlement")
        if not math.isfinite(actual_usd) or actual_usd < 0 or actual_usd > self.local_reservations[key] + 1e-12:
            raise BudgetExceeded("invalid exploratory settlement")
        self.store.write("settlements", key, {"actual_usd": actual_usd})
        self.local_settlements[key] = actual_usd
