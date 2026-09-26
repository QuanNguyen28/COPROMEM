"""Strict whole-response JSON transport for exploratory lifecycle generation.

This deliberately has no tool fields.  Executor actions continue to use the
native-tool transport; lifecycle generation is a separately preregistered,
provider-neutral text contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import time
from typing import Any, Callable, Mapping
import urllib.request

from .appworld_live_smoke import LOCKED_MODEL, LOCKED_OPENROUTER_URL


class StrictLifecycleJsonError(RuntimeError):
    pass


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StrictLifecycleJsonError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def parse_exact_json_object(text: str, schema_name: str) -> dict[str, Any]:
    """Reject any non-object, surrounding text, duplicate key, or invalid shape."""
    if not isinstance(text, str) or not text or text != text.strip() or not text.startswith("{"):
        raise StrictLifecycleJsonError("response is not exactly one JSON object")
    try:
        decoder = json.JSONDecoder(object_pairs_hook=_reject_duplicates)
        value, index = decoder.raw_decode(text)
    except (json.JSONDecodeError, StrictLifecycleJsonError) as exc:
        raise StrictLifecycleJsonError("malformed lifecycle JSON") from exc
    if index != len(text) or not isinstance(value, dict):
        raise StrictLifecycleJsonError("response is not exactly one JSON object")
    _validate_schema(value, schema_name)
    return value


def _is_bool(value: Any) -> bool:
    return isinstance(value, bool)


def _validate_schema(value: Mapping[str, Any], schema_name: str) -> None:
    if schema_name == "copromem_complexity_v1":
        if set(value) != {"is_compound", "rationale"} or not _is_bool(value["is_compound"]) or not isinstance(value["rationale"], str):
            raise StrictLifecycleJsonError("invalid copromem complexity schema")
        return
    if schema_name == "copromem_subgoals_v1":
        if set(value) != {"subgoals"} or not isinstance(value["subgoals"], list) or not 2 <= len(value["subgoals"]) <= 3:
            raise StrictLifecycleJsonError("invalid copromem subgoals schema")
        for subgoal in value["subgoals"]:
            if not isinstance(subgoal, dict) or set(subgoal) != {"description", "is_atomic"} or not isinstance(subgoal["description"], str) or not subgoal["description"].strip() or not _is_bool(subgoal["is_atomic"]):
                raise StrictLifecycleJsonError("invalid copromem subgoal")
        return
    if schema_name == "reme_failure_reflection_v1":
        if set(value) != {"failure_evidence_ids", "memory_text"} or not isinstance(value["failure_evidence_ids"], list) or not all(isinstance(item, str) and item for item in value["failure_evidence_ids"]) or not isinstance(value["memory_text"], str):
            raise StrictLifecycleJsonError("invalid ReMe reflection schema")
        return
    raise StrictLifecycleJsonError(f"unknown lifecycle schema: {schema_name}")


@dataclass(frozen=True)
class LifecycleJsonOutcome:
    output: Mapping[str, Any]
    prompt_tokens: int
    completion_tokens: int
    actual_usd: float
    latency_seconds: float
    finish_reason: str
    model: str


class LockedLifecycleJsonTransport:
    """The only paid lifecycle text boundary for the JSON successor protocol."""
    def __init__(self, *, api_key: str, ledger: Any, sender: Callable[[dict[str, Any]], dict[str, Any]] | None = None) -> None:
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY required")
        self.api_key, self.ledger, self.sender = api_key, ledger, sender

    @staticmethod
    def request_body(*, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        return {
            "model": LOCKED_MODEL,
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            "max_tokens": 1024,
            "stream": False,
            "reasoning_effort": "none",
            "provider": {"only": ["deepseek"], "allow_fallbacks": False, "require_parameters": True},
        }

    def dispatch(self, *, key: str, metadata: dict[str, Any], system_prompt: str, user_prompt: str, schema_name: str, upper_usd: float) -> LifecycleJsonOutcome:
        self.ledger.reserve(key, upper_usd, metadata)
        body = self.request_body(system_prompt=system_prompt, user_prompt=user_prompt)
        started = time.perf_counter()
        try:
            if self.sender is not None:
                raw = self.sender(body)
            else:
                request = urllib.request.Request(LOCKED_OPENROUTER_URL, data=json.dumps(body).encode("utf-8"), headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(request, timeout=45) as response:
                    raw = json.loads(response.read().decode("utf-8"))
        except Exception:
            raise StrictLifecycleJsonError("locked lifecycle JSON dispatch failed") from None
        choice = (raw.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content")
        usage = raw.get("usage") or {}
        if usage.get("cost") is None:
            raise StrictLifecycleJsonError("OpenRouter lifecycle cost missing; reservation retained")
        actual = float(usage["cost"])
        self.ledger.settle(key, actual)
        reasoning = int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or usage.get("reasoning_tokens") or 0)
        provider = raw.get("provider") or (raw.get("metadata") or {}).get("provider")
        response_model = str(raw.get("model"))
        raw_hash = sha256(content.encode("utf-8")).hexdigest() if isinstance(content, str) else None
        valid_json = False
        output: dict[str, Any] = {}
        try:
            output = parse_exact_json_object(content, schema_name)
            valid_json = True
        except StrictLifecycleJsonError:
            pass
        outcome = LifecycleJsonOutcome(output, int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0), actual, time.perf_counter() - started, str(choice.get("finish_reason")), response_model)
        validation = {"exact_model": response_model == LOCKED_MODEL, "resolved_provider": str(provider).lower() == "deepseek", "zero_reasoning": reasoning == 0, "non_truncated_finish": outcome.finish_reason not in {"length", "content_filter", "error"}, "exact_valid_json": valid_json}
        if hasattr(self.ledger, "store"):
            self.ledger.store.write("locked_lifecycle_json", key, {"schema_name": schema_name, "request_body_sha256": sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(), "raw_response_sha256": raw_hash, "parsed_output_sha256": sha256(json.dumps(output, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest() if valid_json else None, "response_model": response_model, "provider": provider, "finish_reason": outcome.finish_reason, "usage": {"prompt_tokens": outcome.prompt_tokens, "completion_tokens": outcome.completion_tokens, "reasoning_tokens": reasoning}, "latency_seconds": outcome.latency_seconds, "actual_usd": actual, "validation": validation})
        if not all(validation.values()):
            raise StrictLifecycleJsonError("locked lifecycle JSON fidelity gate failed")
        return outcome
