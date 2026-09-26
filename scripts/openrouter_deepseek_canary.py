"""One-shot, append-only OpenRouter/DeepSeek route canary.

This is intentionally not an AppWorld run.  It sends exactly one non-streaming
tool-call request after reserving USD 0.01.  It never serializes the API key or
full response headers.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from copromem.checkpoints import RunStore
from copromem.providers import BudgetLedger


# New immutable successor: the preceding failed canary remains untouched in its
# own ledger, including its retained USD 0.01 reservation.
ROOT = Path("artifacts/research/reme_copromem_comparison/openrouter_deepseek_successor_canary_corrected")
URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "deepseek/deepseek-v4.1-flash"
RESERVATION_USD = 0.01


def dotenv_key(path: Path) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("OPENROUTER_API_KEY="):
            value = line.split("=", 1)[1].strip().strip("\"'")
            return value or None
    return None


def sanitized_headers(headers: Any) -> dict[str, str]:
    """Keep only route-identifying, non-sensitive headers."""
    allowed = {"x-request-id", "request-id", "x-openrouter-provider", "x-openrouter-model"}
    return {key.lower(): value for key, value in headers.items() if key.lower() in allowed}


def provider_identity(payload: dict[str, Any], headers: dict[str, str]) -> str | None:
    for value in (
        payload.get("provider"),
        payload.get("provider_name"),
        (payload.get("metadata") or {}).get("provider"),
        headers.get("x-openrouter-provider"),
    ):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def safe_http_error(exc: urllib.error.HTTPError) -> dict[str, Any]:
    code = None
    message = None
    try:
        body = json.loads(exc.read().decode("utf-8", errors="replace"))
        error = body.get("error") or {}
        code = error.get("code") or error.get("type")
        message = str(error.get("message") or "")[:300]
    except Exception:
        pass
    return {"status": "http_error", "http_status": exc.code, "error_code": code, "message": message}


def main() -> int:
    key = os.environ.get("OPENROUTER_API_KEY") or dotenv_key(Path(".env"))
    if not key:
        print("OPENROUTER_API_KEY unavailable; no request sent", file=sys.stderr)
        return 2
    store = RunStore(ROOT)
    store.write(
        "predecessor",
        "failed_canary",
        {
            "root": "artifacts/research/reme_copromem_comparison/openrouter_deepseek_successor_canary",
            "carried_reservation_usd": RESERVATION_USD,
            "status": "retained; predecessor immutable",
        },
    )
    ledger = BudgetLedger(store, max_usd=RESERVATION_USD, max_attempts=1)
    reservation = ledger.reserve(RESERVATION_USD)
    schema = {
        "type": "object",
        "properties": {"status": {"type": "string", "enum": ["ok"]}},
        "required": ["status"],
        "additionalProperties": False,
    }
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Call canary exactly once with status ok. Do not write prose."}],
        "max_tokens": 128,
        "stream": False,
        "reasoning_effort": "none",
        "provider": {"only": ["deepseek"], "allow_fallbacks": False, "require_parameters": True},
        "tools": [{"type": "function", "function": {"name": "canary", "description": "Return fixed status.", "parameters": schema}}],
        # The available DeepSeek endpoint advertises auto but not forced tool
        # selection.  We still require exactly one voluntary tool call below.
        "tool_choice": "auto",
    }
    store.write("route", reservation, {"endpoint": URL, "model": MODEL, "provider_only": ["deepseek"], "allow_fallbacks": False, "reasoning_effort": "none", "stream": False, "max_tokens": 128, "reservation_usd": RESERVATION_USD, "pricing_snapshot_usd_per_million": {"prompt": 0.30, "completion": 1.20}})
    request = urllib.request.Request(URL, data=json.dumps(body).encode("utf-8"), headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "X-OpenRouter-Metadata": "enabled"}, method="POST")
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
            status = response.status
            headers = sanitized_headers(response.headers)
    except urllib.error.HTTPError as exc:
        store.write("transport", reservation, safe_http_error(exc))
        print("canary HTTP failure; reservation retained", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        store.write("transport", reservation, {"status": "transport_failure", "error_type": type(exc).__name__})
        print("canary transport failure; reservation retained", file=sys.stderr)
        return 1
    latency = time.perf_counter() - started
    choice = (payload.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    calls = message.get("tool_calls") or []
    parsed: Any = None
    valid_arguments = False
    if len(calls) == 1 and ((calls[0].get("function") or {}).get("name") == "canary"):
        try:
            parsed = json.loads(calls[0]["function"]["arguments"])
            valid_arguments = parsed == {"status": "ok"}
        except (KeyError, TypeError, json.JSONDecodeError):
            pass
    usage = payload.get("usage") or {}
    details = usage.get("completion_tokens_details") or {}
    reasoning_tokens = int(details.get("reasoning_tokens") or usage.get("reasoning_tokens") or 0)
    cost = usage.get("cost")
    if cost is not None:
        try:
            ledger.settle(reservation, float(cost))
        except Exception as exc:
            store.write("budget", reservation, {"status": "settlement_failure", "error_type": type(exc).__name__})
            print("canary budget settlement failure", file=sys.stderr)
            return 1
    resolved_provider = provider_identity(payload, headers)
    valid = {
        "http_200": status == 200,
        "exact_model": payload.get("model") == MODEL,
        "resolved_deepseek_provider": isinstance(resolved_provider, str) and resolved_provider.lower() == "deepseek",
        "exactly_one_valid_tool_call": valid_arguments,
        "non_truncated": choice.get("finish_reason") == "tool_calls",
        "non_thinking": reasoning_tokens == 0 and not message.get("reasoning_content") and not message.get("reasoning"),
        "actual_cost_recorded": cost is not None,
    }
    store.write("result", reservation, {"http_status": status, "response_model": payload.get("model"), "resolved_provider": resolved_provider, "finish_reason": choice.get("finish_reason"), "tool_call_count": len(calls), "parsed_tool_arguments": parsed, "usage": {"prompt_tokens": int(usage.get("prompt_tokens") or 0), "completion_tokens": int(usage.get("completion_tokens") or 0), "reasoning_tokens": reasoning_tokens}, "latency_seconds": latency, "actual_cost_usd": float(cost) if cost is not None else None, "cost_status": "provider_reported" if cost is not None else "reservation_retained", "safe_response_headers": headers, "validation": valid})
    print(json.dumps({"reservation": reservation, "passed": all(valid.values())}))
    return 0 if all(valid.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
