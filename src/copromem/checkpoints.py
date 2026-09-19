"""Immutable public handoffs and recorded, matched provider requests.

The cache couples *identical* requests within a replicate. It never couples different
prompts and is not a claim that a remote provider is deterministic. Logical per-arm
usage and physical collection usage must be reported separately.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


def canonical(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def matched_seed(base: int, task_id: str, stage: str, replicate: int = 0) -> int:
    return int(digest([base, task_id, stage, replicate])[:8], 16) % (2**31)


class IntegrityError(ValueError):
    """A saved immutable object disagrees with its content address."""


class RecordedCallError(RuntimeError):
    """A provider failure whose safe details are already in the run store."""


class RunStore:
    """Write-once JSON objects. Existing objects may only be read or verified."""

    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root is not None else None
        self._objects: dict[tuple[str, str], str] = {}

    @staticmethod
    def _validate_components(kind: str, key: str) -> None:
        if any(
            not isinstance(part, str)
            or part in {"", ".", ".."}
            or any(char in part for char in '/\\:*?"<>|\x00')
            or part.endswith((" ", "."))
            for part in (kind, key)
        ):
            raise ValueError("store keys must be plain path components")

    def read(self, kind: str, key: str) -> dict[str, Any] | None:
        self._validate_components(kind, key)
        if self.root is not None:
            path = self.root / kind / f"{key}.json"
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        raw = self._objects.get((kind, key))
        return json.loads(raw) if raw is not None else None

    def write(self, kind: str, key: str, value: dict[str, Any]) -> None:
        self._validate_components(kind, key)
        serialized = canonical(value)
        existing = self.read(kind, key)
        if existing is not None:
            if canonical(existing) != serialized:
                raise IntegrityError(f"refusing to overwrite {kind}/{key}")
            return
        if self.root is not None:
            folder = self.root / kind
            folder.mkdir(parents=True, exist_ok=True)
            with (folder / f"{key}.json").open("x", encoding="utf-8") as stream:
                stream.write(serialized + "\n")
        self._objects[(kind, key)] = serialized

    def bind_provenance(self, value: dict[str, Any]) -> None:
        """Resume only the recorded code/environment, before any paid calls.

        Older runs used digest-named provenance records. Check those as well so a
        changed miner cannot silently mix newly collected evidence into that run.
        """
        if self.root is not None:
            previous = [
                self.read("provenance", path.stem)
                for path in sorted((self.root / "provenance").glob("*.json"))
            ]
        else:
            previous = [
                json.loads(raw)
                for (kind, _), raw in self._objects.items()
                if kind == "provenance"
            ]
        if any(canonical(item) != canonical(value) for item in previous):
            raise IntegrityError(
                "code/environment provenance changed; use a new preregistered cycle "
                "and directory, or audit the old run offline"
            )
        self.write("provenance", digest(value), value)


@dataclass(frozen=True)
class PlannerCheckpoint:
    task_id: str
    question: str
    split: str
    family: str
    replicate: int
    artifact_json: str
    generation_id: str

    @property
    def checkpoint_id(self) -> str:
        return digest(asdict(self))

    def artifact(self) -> dict[str, Any]:
        """A new deep copy on each access; callers cannot mutate shared state."""
        return json.loads(self.artifact_json)

    def save(self, store: RunStore) -> None:
        store.write("checkpoints", self.checkpoint_id, asdict(self))

    @classmethod
    def load(cls, store: RunStore, checkpoint_id: str) -> PlannerCheckpoint:
        payload = store.read("checkpoints", checkpoint_id)
        if payload is None:
            raise FileNotFoundError(checkpoint_id)
        checkpoint = cls(**payload)
        if checkpoint.checkpoint_id != checkpoint_id:
            raise IntegrityError("checkpoint content hash mismatch")
        return checkpoint


@dataclass(frozen=True)
class Generation:
    request_id: str
    response_json: str
    reused: bool

    @property
    def text(self) -> str:
        return json.loads(self.response_json)["text"]

    @property
    def usage(self) -> dict[str, Any]:
        return json.loads(self.response_json)["usage"]

    @property
    def model(self) -> str:
        return json.loads(self.response_json)["model"]


class GenerationService:
    """Provider-independent recording boundary with safe failure logging."""

    def __init__(self, client: Any, store: RunStore, namespace: str):
        self.client = client
        self.store = store
        self.namespace = namespace
        self.references: list[Generation] = []
        self.physical: list[Generation] = []
        self.failures: list[dict[str, Any]] = []

    def call(self, system: str, user: str, max_tokens: int, seed: int) -> Generation:
        request = {
            "namespace": self.namespace,
            "model": str(getattr(self.client, "model", type(self.client).__name__)),
            "provider_configuration": getattr(self.client, "request_configuration", {}),
            "temperature": 0,
            "seed": seed,
            "max_tokens": max_tokens,
            "system": system,
            "user": user,
        }
        key = digest(request)
        record = self.store.read("calls", key)
        reused = record is not None
        if record is None:
            started = time.time_ns()
            before_attempts = getattr(self.client, "http_attempts", 0)
            try:
                parameters = inspect.signature(self.client.chat).parameters
                kwargs: dict[str, Any] = {"max_tokens": max_tokens}
                if "seed" in parameters:
                    kwargs["seed"] = seed
                result = self.client.chat(system, user, **kwargs)
                response = {
                    "text": result.text,
                    "usage": asdict(result.usage),
                    "model": result.model,
                    "metadata": getattr(result, "metadata", {}),
                }
                record = {
                    "request": request,
                    "response": response,
                    "response_sha256": digest(response),
                    "started_ns": started,
                    "http_attempts": getattr(
                        self.client, "http_attempts", before_attempts + 1
                    )
                    - before_attempts,
                    "seed_forwarded": "seed" in parameters,
                }
                self.store.write("calls", key, record)
            except Exception as exc:  # noqa: BLE001 -- provider boundary; record and isolate every ordinary failure
                # Do not log exception messages: providers may echo credentials.
                failure = {
                    "request": request,
                    "request_id": key,
                    "started_ns": started,
                    "error_type": type(exc).__name__,
                    "http_attempts": getattr(
                        self.client, "http_attempts", before_attempts + 1
                    )
                    - before_attempts,
                }
                self.store.write("failures", f"{key}-{started}", failure)
                self.failures.append(failure)
                raise RecordedCallError(
                    f"recorded {type(exc).__name__} for request {key}"
                ) from None
        if (
            digest(record["request"]) != key
            or digest(record["response"]) != record["response_sha256"]
        ):
            raise IntegrityError(
                "saved provider request/response failed integrity check"
            )
        generation = Generation(key, canonical(record["response"]), reused)
        self.references.append(generation)
        if not reused:
            self.physical.append(generation)
        return generation

    def costs(self) -> dict[str, Any]:
        unique = {item.request_id: item for item in self.references}
        ledger = getattr(self.client, "ledger", None)
        return {
            "physical_calls_this_invocation": len(self.physical),
            "physical_usd_this_invocation": sum(
                item.usage["usd"] for item in self.physical
            ),
            "unique_calls_in_protocol": len(unique),
            "unique_usd_in_protocol": sum(
                item.usage["usd"] for item in unique.values()
            ),
            "logical_call_references": len(self.references),
            "cache_reuses": sum(item.reused for item in self.references),
            "recorded_failures_this_invocation": len(self.failures),
            "http_attempts_this_client": getattr(self.client, "http_attempts", None),
            "failed_http_attempts_this_client": getattr(
                self.client, "failed_http_attempts", None
            ),
            "budget_charged_or_reserved_usd": ledger.charged_or_reserved
            if ledger
            else None,
            "budget_total_reservations": len(ledger.reservations) if ledger else None,
            "budget_unsettled_reservations": len(
                ledger.reservations.keys() - ledger.settlements.keys()
            )
            if ledger
            else None,
        }
