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
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

try:  # ``fcntl`` is present in the supported Linux runner environment.
    import fcntl
except ImportError:  # Allow Windows-side static imports and fixture tests.
    fcntl = None  # type: ignore[assignment]

URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "deepseek/deepseek-v4.1-flash"
# The direct DeepSeek endpoint became unavailable during the exposed pilot on
# 2026-10-02.  This separately versioned successor pins DeepInfra for every
# chat call while retaining the exact same OpenRouter model ID.  Fallbacks
# remain disabled, so all experimental arms share one explicit serving route.
PROVIDER = "deepinfra"
ENDPOINTS_URL = f"https://openrouter.ai/api/v1/models/{MODEL}/endpoints"
# These limits are frozen in the corrected fixed/dynamic manifest.  They must
# be expressed in tokens, never in UTF-8 bytes divided by an assumed average.
# ``o200k_base`` is a real BPE tokenizer available in the pinned ReMe service
# environment.  It is used as a conservative, reproducible compatibility
# counter for the OpenRouter Chat Completions payload; a missing tokenizer is
# a fail-closed pre-dispatch error rather than a reason to guess.
INPUT_TOKEN_CEILING = int(os.environ.get("OFFICIAL_PILOT_INPUT_TOKEN_CEILING", "32768"))
MAX_OUTPUT_TOKENS = int(os.environ.get("OFFICIAL_PILOT_MAX_COMPLETION_TOKENS", "2048"))
TOKENIZER_NAME = "o200k_base"
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


class TruncationTermination(DispatchFailure):
    """A returned length-limited response must never be executed as code."""
    def __init__(self, prompt_tokens: int, completion_tokens: int) -> None:
        super().__init__("completion token ceiling reached")
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


def verify_locked_chat_route_available(timeout: float = 15.0) -> dict[str, Any]:
    """Fail before paid dispatch when the frozen provider endpoint is down.

    OpenRouter's public endpoint inventory reports each hosting provider and a
    numeric status.  The frozen direct DeepSeek route is admissible only when
    exactly one matching endpoint reports status zero.  This check neither
    needs a credential nor opens a model/task payload.
    """
    try:
        request = urllib.request.Request(ENDPOINTS_URL, method="GET",
                                         headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        raise DispatchFailure("locked chat route availability could not be verified") from None
    root = data.get("data") if isinstance(data, dict) else None
    endpoints = root.get("endpoints") if isinstance(root, dict) else None
    matches = [item for item in endpoints or [] if isinstance(item, dict) and
               str(item.get("provider_name") or "").strip().lower() == PROVIDER]
    if len(matches) != 1:
        raise DispatchFailure("locked chat provider endpoint is absent or ambiguous")
    status = matches[0].get("status")
    try:
        normalized_status = int(status)
    except (TypeError, ValueError):
        raise DispatchFailure("locked chat provider endpoint status is malformed") from None
    if normalized_status != 0:
        raise DispatchFailure("locked chat provider endpoint is unavailable")
    return {"model": MODEL, "provider": PROVIDER, "status": normalized_status,
            "endpoint_name": str(matches[0].get("name") or "")[:256] or None}


def count_chat_tokens(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> int:
    """Count the canonical chat payload with a real BPE tokenizer.

    The provider does not expose a DeepSeek V4.1 tokenizer endpoint.  This
    deliberately uses the pinned ``tiktoken`` BPE rather than a byte heuristic
    and includes tool schemas in the counted canonical request.  The small
    per-message framing allowance is intentionally conservative.
    """
    try:
        import tiktoken
        encoding = tiktoken.get_encoding(TOKENIZER_NAME)
    except Exception as exc:  # no approximate fallback is scientifically safe
        raise DispatchFailure("required tokenizer unavailable") from exc
    payload: dict[str, Any] = {"messages": messages}
    if tools:
        payload["tools"] = tools
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"))
    return len(encoding.encode(canonical)) + (4 * len(messages)) + 3


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
    def __init__(self, path: pathlib.Path, cap_usd: float,
                 call_limits: dict[str, int] | None = None) -> None:
        self.path, self.cap_usd = path, cap_usd
        raw_limits = call_limits
        if raw_limits is None and os.environ.get("OFFICIAL_PILOT_CALL_LIMITS"):
            try:
                raw_limits = json.loads(os.environ["OFFICIAL_PILOT_CALL_LIMITS"])
            except json.JSONDecodeError as exc:
                raise DispatchFailure("registered provider call limits are malformed") from exc
        self.call_limits = {str(key): int(value) for key, value in (raw_limits or {}).items()}
        if any(value < 0 for value in self.call_limits.values()):
            raise DispatchFailure("registered provider call limits must be nonnegative")
        self._retry_io(lambda: path.parent.mkdir(parents=True, exist_ok=True), "create ledger directory")

    @staticmethod
    def _role_bucket(role: Any) -> str | None:
        text = str(role or "")
        if text.startswith("executor:"):
            return "executor"
        if text.startswith("reme_lifecycle:"):
            return "reme_lifecycle"
        if text.startswith("reme_embedding:"):
            return "reme_embedding"
        if text.startswith("copromem_decomposition:"):
            return "copromem_decomposition"
        # ReasoningBank's judge, extractor, and embeddings are separate
        # provider boundaries.  They intentionally share this transport's
        # accounting, retry, pricing, and route validation rather than
        # duplicating an OpenRouter client.
        if text == "reasoningbank_judge":
            return "reasoningbank_judge"
        if text == "reasoningbank_extraction":
            return "reasoningbank_extraction"
        if text == "reasoningbank_embedding":
            return "reasoningbank_embedding"
        return None

    @staticmethod
    def _transient_io(exc: OSError) -> bool:
        # drvfs can briefly deny an append while Windows indexes or scans an
        # E: artifact.  These failures are transport contention, never a reason
        # to abandon a provider response that has already been received.
        return isinstance(exc, PermissionError) or exc.errno in {11, 13, 16, 26, 116}

    def _retry_io(self, operation: Any, label: str) -> Any:
        deadline = time.monotonic() + float(os.environ.get("COPROMEM_LEDGER_IO_RETRY_SECONDS", "90"))
        delay = 0.05
        while True:
            try:
                return operation()
            except OSError as exc:
                if not self._transient_io(exc) or time.monotonic() >= deadline:
                    raise DispatchFailure(f"durable ledger {label} failed: {exc}") from exc
                time.sleep(delay)
                delay = min(delay * 2.0, 1.0)

    def _read_records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        def load() -> list[dict[str, Any]]:
            return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line]
        try:
            return self._retry_io(load, "read")
        except json.JSONDecodeError as exc:
            raise DispatchFailure("durable ledger is malformed") from exc

    def _record_present(self, record: dict[str, Any]) -> bool:
        for observed in self._read_records():
            if observed == record:
                return True
            if observed.get("event") == record.get("event") and observed.get("id") == record.get("id"):
                raise DispatchFailure("durable ledger contains conflicting duplicate record")
        return False

    def _append(self, record: dict[str, Any]) -> None:
        # Retrying a completed append must never duplicate an accounting row.
        # Check the durable bytes after an I/O exception before attempting again.
        line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        def append_once() -> None:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
        deadline = time.monotonic() + float(os.environ.get("COPROMEM_LEDGER_IO_RETRY_SECONDS", "90"))
        delay = 0.05
        while True:
            try:
                append_once()
                return
            except OSError as exc:
                if self._transient_io(exc) and self._record_present(record):
                    return
                if not self._transient_io(exc) or time.monotonic() >= deadline:
                    raise DispatchFailure(f"durable ledger append failed: {exc}") from exc
                time.sleep(delay)
                delay = min(delay * 2.0, 1.0)

    @contextmanager
    def _locked_file(self):
        """Use an advisory file lock in production; fixture imports need none.

        Detached pilot dispatch is supported only from Linux, where ``fcntl``
        is mandatory.  Windows intentionally gets no false claim of a
        multiprocess-safe production lock; it is used here only for offline
        inspection and deterministic tests.
        """
        lock = self.path.with_suffix(".lock")
        handle = self._retry_io(lambda: lock.open("a+"), "lock open")
        try:
            if fcntl is not None:
                fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(handle, fcntl.LOCK_UN)
                handle.close()
        except BaseException:
            # Preserve DispatchFailure and provider safety semantics unchanged.
            raise

    def _exposure(self) -> float:
        latest: dict[str, float] = {}
        for item in self._read_records():
            if item.get("event") == "reserve":
                latest[item["id"]] = float(item["usd"])
            elif item.get("event") == "settle" and item["id"] in latest:
                latest[item["id"]] = float(item["usd"])
        return sum(latest.values())

    def _call_state(self) -> tuple[dict[str, float], set[str]]:
        """Return reservations and settled IDs from durable append-only rows."""
        reserved: dict[str, float] = {}
        settled: set[str] = set()
        for item in self._read_records():
            if item.get("event") == "reserve":
                reserved[str(item["id"])] = float(item["usd"])
            elif item.get("event") == "settle":
                settled.add(str(item["id"]))
        return reserved, settled

    def reserve(self, call_id: str, upper_usd: float, metadata: dict[str, Any]) -> None:
        with self._locked_file():
            reserved, _ = self._call_state()
            if call_id in reserved:
                raise DispatchFailure("duplicate provider call ID")
            bucket = self._role_bucket(metadata.get("role"))
            if self.call_limits:
                historical = metadata.get("role") == "historical_carry_forward"
                if not historical and (bucket is None or bucket not in self.call_limits):
                    raise DispatchFailure("unregistered provider call role")
                if not historical:
                    used = 0
                    for row in self._read_records():
                        if row.get("event") == "reserve" and self._role_bucket(row.get("role")) == bucket:
                            used += 1
                    if used >= self.call_limits[bucket]:
                        raise DispatchFailure(f"registered {bucket} call limit would be exceeded")
            if upper_usd < 0 or self._exposure() + upper_usd > self.cap_usd:
                raise DispatchFailure("USD cap would be exceeded")
            self._append({"event": "reserve", "id": call_id, "usd": upper_usd, **metadata})

    def settle(self, call_id: str, actual_usd: float, metadata: dict[str, Any]) -> None:
        with self._locked_file():
            reserved, settled = self._call_state()
            if call_id not in reserved or call_id in settled:
                raise DispatchFailure("unknown or already-settled provider call")
            if actual_usd < 0 or actual_usd > reserved[call_id]:
                raise DispatchFailure("provider settlement exceeds reserved exposure")
            self._append({"event": "settle", "id": call_id, "usd": actual_usd, **metadata})
            if self._exposure() > self.cap_usd:
                raise DispatchFailure("provider cost exceeded USD cap")


class LockedChatCompletions:
    def __init__(self, api_key: str, ledger: AppendOnlyLedger, progress: pathlib.Path, role: str) -> None:
        self.api_key, self.ledger, self.progress, self.role = api_key, ledger, progress, role
        # Sanitized terminal metadata only.  The execution boundary needs this
        # to bind a settled zero-action length termination; it never retains
        # model content or request messages.
        self.last_record: dict[str, Any] | None = None

    def _progress(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        with self.progress.open("a", encoding="utf-8") as handle:
            handle.write(line); handle.flush(); os.fsync(handle.fileno())

    @staticmethod
    def _resolved_provider(data: dict[str, Any]) -> tuple[str, str]:
        """Return the selected provider and its evidence domain.

        OpenRouter historically emitted a top-level ``provider`` field.  Its
        current Chat Completions contract exposes routing evidence under
        ``openrouter_metadata`` when the caller opts in with
        ``X-OpenRouter-Metadata: enabled``.  Accept only an explicitly selected
        endpoint from that structure; never infer a provider from the model
        name, summary prose, or the request itself.
        """
        metadata = data.get("openrouter_metadata")
        if isinstance(metadata, dict):
            endpoints = metadata.get("endpoints")
            available = endpoints.get("available") if isinstance(endpoints, dict) else None
            if isinstance(available, list):
                selected = [item for item in available
                            if isinstance(item, dict) and item.get("selected") is True]
                if len(selected) == 1:
                    provider = str(selected[0].get("provider") or "").strip().lower()
                    if provider:
                        return provider, "openrouter_metadata.selected_endpoint"
        legacy = str(data.get("provider") or "").strip().lower()
        return (legacy, "legacy_top_level") if legacy else ("", "absent")

    def create(self, *, model: str, messages: list[dict[str, Any]], stream: bool = False,
               max_tokens: int | None = None, tools: list[dict[str, Any]] | None = None,
               tool_choice: str | dict[str, Any] | None = None,
               parallel_tool_calls: bool | None = None, temperature: float = 0.7,
               top_p: float = 1.0, seed: int | None = None, **_: Any) -> Any:
        if model != MODEL:
            raise DispatchFailure("model substitution rejected")
        if stream:
            # The transport returns an SDK-compatible iterator after its single
            # non-streaming request.  A true streaming network request is not
            # permitted by the frozen route.
            pass
        if tool_choice not in (None, "auto"):
            raise DispatchFailure("forced tool selection rejected")
        if parallel_tool_calls not in (None, False):
            raise DispatchFailure("parallel tool calls rejected")
        if not 0.0 <= float(temperature) <= 2.0 or not 0.0 < float(top_p) <= 1.0:
            raise DispatchFailure("generation controls rejected")
        lifecycle_role = self.role.startswith(("reme_lifecycle", "copromem_decomposition"))
        effective_temperature = 0.0 if lifecycle_role else float(temperature)
        estimated_input_tokens = count_chat_tokens(messages, tools)
        # A versioned protocol may authorize a larger ceiling only for offline
        # lifecycle/decomposition prompts.  Executor conversations retain the
        # frozen universal executor ceiling regardless of this setting.
        ceiling = (int(os.environ.get("OFFICIAL_PILOT_LIFECYCLE_INPUT_TOKEN_CEILING", INPUT_TOKEN_CEILING))
                   if lifecycle_role else INPUT_TOKEN_CEILING)
        if estimated_input_tokens > ceiling:
            raise ContextCeilingTermination(estimated_input_tokens, ceiling)
        output = MAX_OUTPUT_TOKENS if max_tokens is None else min(int(max_tokens), MAX_OUTPUT_TOKENS)
        bound = estimated_input_tokens * INPUT_PRICE + output * OUTPUT_PRICE
        call_id = f"{time.time_ns()}-{self.role}"
        meta = {"role": self.role, "model": MODEL, "provider_only": PROVIDER,
                "stream": False, "max_completion_tokens": output,
                "estimated_input_tokens": estimated_input_tokens,
                "tokenizer": TOKENIZER_NAME, "temperature": effective_temperature,
                "top_p": float(top_p), "seed": seed}
        self.ledger.reserve(call_id, bound, meta)
        body = {"model": MODEL, "messages": messages, "stream": False, "max_tokens": output,
                "temperature": effective_temperature, "top_p": float(top_p),
                "reasoning_effort": "none", "provider": {"only": [PROVIDER], "allow_fallbacks": False,
                "require_parameters": True, "max_price": {"prompt": 0.30, "completion": 1.20}}}
        if tools:
            body["tools"] = tools
            body["parallel_tool_calls"] = False
            if tool_choice == "auto": body["tool_choice"] = "auto"
        if seed is not None: body["seed"] = int(seed)
        started = time.perf_counter()
        try:
            request = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
                         "X-OpenRouter-Metadata": "enabled"})
            with urllib.request.urlopen(request, timeout=90) as response:
                raw_response = response.read()
                response_status = int(getattr(response, "status", 0) or 0)
                response_content_type = str(response.headers.get("content-type") or "").split(";", 1)[0].lower()
                response_request_id = str(response.headers.get("x-request-id") or
                                          response.headers.get("x-openrouter-request-id") or "")[:128] or None
                try:
                    data = json.loads(raw_response.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self._progress({"event": "call_response_invalid", "id": call_id, "role": self.role,
                                    "http_status": response_status,
                                    "content_type": response_content_type or None,
                                    "request_id": response_request_id,
                                    "response_length": len(raw_response),
                                    "response_sha256": hashlib.sha256(raw_response).hexdigest()})
                    raise DispatchFailure("OpenRouter returned a non-JSON response") from None
        except Exception as exc:
            self._progress({"event": "call_failed", "id": call_id, "role": self.role,
                            "error_type": type(exc).__name__})
            raise DispatchFailure("locked OpenRouter request failed") from None
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage = data.get("usage") or {}
        provider, provider_evidence = self._resolved_provider(data)
        returned_model = str(data.get("model") or "")
        reasoning = int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
        rejection_reasons = []
        if returned_model != MODEL: rejection_reasons.append("model")
        if provider != PROVIDER: rejection_reasons.append("provider")
        if reasoning != 0: rejection_reasons.append("reasoning_tokens")
        if message.get("reasoning"): rejection_reasons.append("reasoning_content")
        actual = float(usage.get("cost") if usage.get("cost") is not None else bound)
        if rejection_reasons:
            # A successful provider response can be billable even when its
            # route metadata violates the frozen contract.  Settle it before
            # failing closed so the append-only ledger never leaves a phantom
            # reservation or hides paid exposure.
            self.ledger.settle(call_id, actual, {"role": self.role, "model": returned_model or None,
                                                 "provider": provider or None,
                                                 "outcome": "route_rejected"})
            self._progress({"event": "call_route_rejected", "id": call_id, "role": self.role,
                            "expected_model": MODEL, "resolved_model": returned_model or None,
                            "expected_provider": PROVIDER, "resolved_provider": provider or None,
                            "provider_evidence": provider_evidence,
                            "reasoning_tokens": reasoning,
                            "reasoning_content_present": bool(message.get("reasoning")),
                            "rejection_reasons": rejection_reasons, "cost": actual})
            raise DispatchFailure("locked route/model/provider/reasoning validation failed")
        self.ledger.settle(call_id, actual, {"role": self.role, "model": returned_model,
                                             "provider": provider,
                                             "provider_evidence": provider_evidence})
        latency = time.perf_counter() - started
        content = message.get("content") or ""
        self._progress({"event": "call_settled", "id": call_id, "role": self.role, "model": returned_model,
                        "provider": provider, "provider_evidence": provider_evidence,
                        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                        "completion_tokens": int(usage.get("completion_tokens") or 0),
                        "reasoning_tokens": reasoning, "latency": latency, "cost": actual,
                        "finish_reason": choice.get("finish_reason"), "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
                        "content_length":len(content), "tool_call_present":bool(message.get("tool_calls"))})
        self.last_record = {"id": call_id, "role": self.role, "model": returned_model,
                            "provider": provider, "provider_evidence": provider_evidence,
                            "finish_reason": choice.get("finish_reason"),
                            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                            "completion_tokens": int(usage.get("completion_tokens") or 0),
                            "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
                            "tool_call_present": bool(message.get("tool_calls"))}
        self.last_accepted_prompt_tokens = int(usage.get("prompt_tokens") or 0)
        if choice.get("finish_reason") == "length":
            raise TruncationTermination(int(usage.get("prompt_tokens") or estimated_input_tokens),
                                        int(usage.get("completion_tokens") or output))
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
