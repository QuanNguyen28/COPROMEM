"""Fail-closed non-streaming OpenRouter client with OpenAI SDK-shaped replies.

This module is an interface adapter only: it forwards unchanged upstream
messages and emulates the SDK's streaming iterator from a single non-streaming
response. It never produces text, tools, memories, or decisions locally.
"""
from __future__ import annotations

import json
import hashlib
import os
import pathlib
import time
import types
import urllib.error
import urllib.request
import fcntl
from dataclasses import dataclass
from typing import Any

URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "deepseek/deepseek-v4.1-flash"
PROVIDER = "deepseek"
# The frozen manifest specifies 16,384 input *tokens*.  The prior adapter
# accidentally treated that as UTF-8 bytes, rejecting an ordinary third agent
# turn far below the registered token ceiling.  English AppWorld prompts are
# bounded using a conservative 4-byte/token transport representation here.
MAX_INPUT_BYTES = 65_536
MAX_OUTPUT_TOKENS = 1024
# Frozen from the successful DeepSeek-only OpenRouter canary route snapshot.
# These values are deliberately higher than the earlier draft-manifest tariff.
INPUT_PRICE = 0.30 / 1_000_000
OUTPUT_PRICE = 1.20 / 1_000_000


class DispatchFailure(BaseException):
    """BaseException stops upstream retry loops after one paid attempt."""


class ContextCeilingTermination(DispatchFailure):
    """Pre-dispatch trajectory terminal condition for the frozen input ceiling."""
    def __init__(self, estimated_prompt_tokens: int, ceiling: int) -> None:
        super().__init__("input token ceiling would be exceeded")
        self.estimated_prompt_tokens = estimated_prompt_tokens
        self.ceiling = ceiling


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    cost: float
    latency: float


class ModelDumpNamespace(types.SimpleNamespace):
    """Small OpenAI/Pydantic compatibility surface FlowLLM reads on streams."""
    def model_dump(self, **_: Any) -> dict[str, Any]:
        return dict(vars(self))


class AppendOnlyLedger:
    def __init__(self, path: pathlib.Path, cap_usd: float) -> None:
        self.path, self.cap_usd = path, cap_usd
        path.parent.mkdir(parents=True, exist_ok=True)

    def _append(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())

    def _exposure(self) -> float:
        latest: dict[str, float] = {}
        if not self.path.exists():
            return 0.0
        for line in self.path.read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            if item.get("event") == "reserve":
                latest[item["id"]] = float(item["usd"])
            elif item.get("event") == "settle" and item["id"] in latest:
                latest[item["id"]] = float(item["usd"])
        return sum(latest.values())

    def reserve(self, call_id: str, upper_usd: float, metadata: dict[str, Any]) -> None:
        lock = self.path.with_suffix(".lock")
        with lock.open("a+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            if upper_usd < 0 or self._exposure() + upper_usd > self.cap_usd:
                raise DispatchFailure("USD cap would be exceeded")
            self._append({"event": "reserve", "id": call_id, "usd": upper_usd, **metadata})
            fcntl.flock(handle, fcntl.LOCK_UN)

    def settle(self, call_id: str, actual_usd: float, metadata: dict[str, Any]) -> None:
        lock = self.path.with_suffix(".lock")
        with lock.open("a+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            self._append({"event": "settle", "id": call_id, "usd": actual_usd, **metadata})
            if self._exposure() > self.cap_usd:
                raise DispatchFailure("provider cost exceeded USD cap")
            fcntl.flock(handle, fcntl.LOCK_UN)


class LockedChatCompletions:
    def __init__(self, api_key: str, ledger: AppendOnlyLedger, progress: pathlib.Path, role: str) -> None:
        self.api_key, self.ledger, self.progress, self.role = api_key, ledger, progress, role

    def _progress(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        with self.progress.open("a", encoding="utf-8") as handle:
            handle.write(line); handle.flush(); os.fsync(handle.fileno())

    def create(self, *, model: str, messages: list[dict[str, Any]], stream: bool = False,
               max_tokens: int | None = None, **_: Any) -> Any:
        if model != MODEL:
            raise DispatchFailure("model substitution rejected")
        encoded = json.dumps(messages, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        estimated_input_tokens = (len(encoded) + 3) // 4
        if len(encoded) > MAX_INPUT_BYTES or estimated_input_tokens > 16_384:
            raise ContextCeilingTermination(estimated_input_tokens, 16_384)
        output = MAX_OUTPUT_TOKENS if max_tokens is None else min(int(max_tokens), MAX_OUTPUT_TOKENS)
        bound = estimated_input_tokens * INPUT_PRICE + output * OUTPUT_PRICE
        call_id = f"{time.time_ns()}-{self.role}"
        meta = {"role": self.role, "model": MODEL, "provider_only": PROVIDER,
                "stream": False, "max_completion_tokens": output,
                "estimated_input_tokens": estimated_input_tokens}
        self.ledger.reserve(call_id, bound, meta)
        body = {"model": MODEL, "messages": messages, "stream": False, "max_tokens": output,
                "reasoning_effort": "none", "provider": {"only": [PROVIDER], "allow_fallbacks": False,
                "require_parameters": True, "max_price": {"prompt": 0.30, "completion": 1.20}}}
        started = time.perf_counter()
        try:
            request = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=90) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            self._progress({"event": "call_failed", "id": call_id, "role": self.role,
                            "error_type": type(exc).__name__})
            raise DispatchFailure("locked OpenRouter request failed") from None
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage = data.get("usage") or {}
        provider = str(data.get("provider") or "").lower()
        returned_model = str(data.get("model") or "")
        reasoning = int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
        if returned_model != MODEL or provider != PROVIDER or reasoning != 0 or message.get("reasoning"):
            self._progress({"event": "call_route_rejected", "id": call_id, "role": self.role})
            raise DispatchFailure("locked route/model/provider/reasoning validation failed")
        actual = float(usage.get("cost") if usage.get("cost") is not None else bound)
        self.ledger.settle(call_id, actual, {"role": self.role, "model": returned_model, "provider": provider})
        latency = time.perf_counter() - started
        content = message.get("content") or ""
        self._progress({"event": "call_settled", "id": call_id, "role": self.role, "model": returned_model,
                        "provider": provider, "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                        "completion_tokens": int(usage.get("completion_tokens") or 0),
                        "reasoning_tokens": reasoning, "latency": latency, "cost": actual,
                        "finish_reason": choice.get("finish_reason"), "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
                        "content_length":len(content), "tool_call_present":bool(message.get("tool_calls"))})
        self.last_accepted_prompt_tokens = int(usage.get("prompt_tokens") or 0)
        result = types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=content,
                reasoning_content=None, tool_calls=message.get("tool_calls")), finish_reason=choice.get("finish_reason"))],
            usage=ModelDumpNamespace(**usage), model=returned_model,
        )
        if not stream:
            return result
        # FlowLLM consumes an iterator. Preserve its source interface while the
        # network request itself remains the locked non-streaming call above.
        def iterator():
            yield types.SimpleNamespace(choices=[types.SimpleNamespace(delta=types.SimpleNamespace(
                content=message.get("content") or "", reasoning_content=None, tool_calls=None))], usage=None)
            yield types.SimpleNamespace(choices=[], usage=ModelDumpNamespace(**usage))
        return iterator()


class LockedOpenAI:
    def __init__(self, *, api_key: str, ledger: AppendOnlyLedger, progress: pathlib.Path, role: str, **_: Any) -> None:
        self.chat = types.SimpleNamespace(completions=LockedChatCompletions(api_key, ledger, progress, role))


class LockedEmbeddings:
    """Ledgered upstream-compatible DashScope embedding boundary.

    This accepts only the embedding operation FlowLLM normally issues.  It
    never exposes a chat endpoint and consequently cannot generate decisions,
    reflections, memories, or actions.
    """
    # DashScope text-embedding-v4 input price is frozen conservatively at
    # USD 1e-7/token (CNY 0.0005/1K with an intentionally adverse 5 CNY/USD).
    USD_PER_INPUT_TOKEN = 0.0000001
    MAX_TOKENS_PER_ITEM = 8192

    def __init__(self, *, api_key: str, base_url: str, ledger: AppendOnlyLedger,
                 progress: pathlib.Path, role: str = "reme_embedding",
                 allowed_model: str = "text-embedding-v4", provider: str = "dashscope",
                 usd_per_input_token: float | None = None, provider_only: str | None = None, **_: Any) -> None:
        self.api_key, self.base_url, self.ledger, self.progress, self.role = (
            api_key, base_url.rstrip("/"), ledger, progress, role)
        self.allowed_model, self.provider = allowed_model, provider
        self.usd_per_input_token = usd_per_input_token or self.USD_PER_INPUT_TOKEN
        self.provider_only = provider_only
        self.last_record: dict[str, Any] | None = None

    def create(self, *, model: str, input: str | list[str], dimensions: int = 1024,
               encoding_format: str = "float", **_: Any) -> Any:
        if model != self.allowed_model or dimensions != 1024 or encoding_format != "float":
            raise DispatchFailure("embedding model/interface substitution rejected")
        items = [input] if isinstance(input, str) else input
        if not items or not all(isinstance(item, str) for item in items):
            raise DispatchFailure("embedding input rejected")
        # The official service batches at <=10.  A byte bound safely exceeds
        # neither provider token allowance nor the frozen per-call reserve.
        if len(items) > 10 or any(len(item.encode("utf-8")) > 32_768 for item in items):
            raise DispatchFailure("embedding batch/input ceiling rejected")
        call_id = f"{time.time_ns()}-{self.role}"
        bound = len(items) * self.MAX_TOKENS_PER_ITEM * self.usd_per_input_token
        self.ledger.reserve(call_id, bound, {"role": self.role, "model": model,
                                            "provider": self.provider, "kind": "embedding"})
        body = {"model": model, "input": input, "dimensions": dimensions,
                "encoding_format": encoding_format}
        if self.provider_only:
            body["provider"] = {"only": [self.provider_only], "allow_fallbacks": False,
                                "require_parameters": True}
        try:
            request = urllib.request.Request(
                self.base_url + "/embeddings", data=json.dumps(body).encode(), method="POST",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
            started = time.perf_counter()
            with urllib.request.urlopen(request, timeout=90) as response:
                data = json.loads(response.read().decode("utf-8"))
                http_status = response.status
                request_id = str(response.headers.get("x-request-id") or response.headers.get("request-id") or "")[:128] or None
        except urllib.error.HTTPError as exc:
            body = exc.read(1024).decode("utf-8", errors="replace")
            code, error_type, message = _sanitize_provider_error(body)
            request_id = str(exc.headers.get("x-request-id") or exc.headers.get("request-id") or "")[:128] or None
            self._progress({"event": "embedding_failed", "id": call_id, "http_status": exc.code,
                            "provider_error_code": code, "provider_error_type": error_type,
                            "request_id": request_id, "message": message})
            raise DispatchFailure("locked embedding request failed") from None
        except Exception as exc:
            self._progress({"event": "embedding_failed", "id": call_id,
                            "error_type": type(exc).__name__, "message": "transport failure"})
            raise DispatchFailure("locked embedding request failed") from None
        usage = data.get("usage") or {}
        resolved_provider = str(data.get("provider") or "").lower()
        if self.provider_only and resolved_provider != self.provider_only.lower():
            self._progress({"event":"embedding_route_rejected", "id":call_id,
                            "expected_provider":self.provider_only, "resolved_provider":resolved_provider or None})
            raise DispatchFailure("embedding provider pin validation failed")
        tokens = int(usage.get("prompt_tokens") or usage.get("total_tokens") or 0)
        actual = tokens * self.usd_per_input_token if tokens else bound
        self.ledger.settle(call_id, actual, {"role": self.role, "model": model,
                                             "provider": self.provider, "kind": "embedding"})
        self._progress({"event": "embedding_settled", "id": call_id, "role": self.role,
                        "model": model, "provider": self.provider, "input_tokens": tokens,
                        "latency": time.perf_counter() - started, "cost": actual})
        self.last_record = {"id": call_id, "http_status": http_status, "request_id": request_id,
                            "resolved_model": str(data.get("model") or model),
                            "resolved_provider": resolved_provider or None,
                            "input_tokens": tokens, "cost": actual,
                            "latency": time.perf_counter() - started}
        entries = [types.SimpleNamespace(**entry) for entry in (data.get("data") or [])]
        return types.SimpleNamespace(data=entries, model=str(data.get("model") or model), usage=types.SimpleNamespace(**usage))

    def _progress(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        with self.progress.open("a", encoding="utf-8") as handle:
            handle.write(line); handle.flush(); os.fsync(handle.fileno())


class LockedEmbeddingOpenAI:
    def __init__(self, **kwargs: Any) -> None:
        self.embeddings = LockedEmbeddings(**kwargs)


def _sanitize_provider_error(body: str) -> tuple[str | None, str | None, str]:
    """Return only schema-level provider diagnostics; never retain payloads."""
    try:
        data = json.loads(body)
        error = data.get("error", data)
        if not isinstance(error, dict): raise ValueError
        code = error.get("code") or error.get("error_code")
        kind = error.get("type") or error.get("error_type")
        message = str(error.get("message") or "provider rejected request")
    except Exception:
        return None, None, "provider returned non-JSON error"
    # Provider prose can echo request content.  Preserve only a short, safe
    # classification-like message, with common secret forms redacted.
    message = message.replace("Bearer ", "Bearer [REDACTED]")[:256]
    return str(code)[:128] if code is not None else None, str(kind)[:128] if kind is not None else None, message
