"""One-shot, fail-closed direct DeepSeek compatibility canary.

The script deliberately reads ``DEEPSEEK_API_KEY`` from its process environment
or a local .env file, but never serializes it, emits it, or places it in a
RunStore record.  It is not an AppWorld executor.
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
from copromem.direct_deepseek_transport import sanitize_http_error, sanitized_request_id
from copromem.providers import BudgetLedger


ROOT = Path("artifacts/research/reme_copromem_comparison/openrouter_brokered_smoke")
BASE_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-flash"
# Official published cache-miss tariff used as a conservative accounting ceiling.
PROMPT_USD_PER_MILLION = 0.30
COMPLETION_USD_PER_MILLION = 1.20
RESERVATION_USD = 0.01


def dotenv_key(path: Path) -> str | None:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("DEEPSEEK_API_KEY="):
            value = line.split("=", 1)[1].strip().strip("\"'")
            return value or None
    return None


def main() -> int:
    key = os.environ.get("DEEPSEEK_API_KEY") or dotenv_key(Path(".env"))
    if not key:
        print("DEEPSEEK_API_KEY unavailable; no request sent", file=sys.stderr)
        return 2

    store = RunStore(ROOT)
    ledger = BudgetLedger(store, max_usd=1.0, max_attempts=78)
    # This happens before constructing the HTTP request and stays charged if the
    # response is absent, malformed, or rejected.
    reservation = ledger.reserve(RESERVATION_USD)
    store.write(
        "direct_deepseek_canary_role",
        reservation,
        {
            "role": "direct_deepseek_tool_and_structured_output_canary",
            "base_url": "https://api.deepseek.com",
            "model": MODEL,
            "model_fallback": False,
            "reasoning_effort": "none",
            "reservation_usd": RESERVATION_USD,
            "pricing_snapshot": {
                "prompt_usd_per_million": PROMPT_USD_PER_MILLION,
                "completion_usd_per_million": COMPLETION_USD_PER_MILLION,
                "cache": "not credited; conservative cache-miss tariff",
            },
        },
    )
    schema = {
        "type": "object",
        "properties": {"status": {"type": "string", "enum": ["ok"]}},
        "required": ["status"],
        "additionalProperties": False,
    }
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Call the canary tool now."}],
        "max_tokens": 128,
        "temperature": 0,
        "stream": False,
        "reasoning_effort": "none",
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "canary",
                    "description": "Return the fixed canary status.",
                    "parameters": schema,
                    "strict": True,
                },
            }
        ],
        "tool_choice": {"type": "function", "function": {"name": "canary"}},
    }
    request = urllib.request.Request(
        BASE_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
            request_id = sanitized_request_id(response.headers)
            status = response.status
    except (urllib.error.HTTPError, OSError, ValueError) as exc:
        diagnostic = (
            sanitize_http_error(exc)
            if isinstance(exc, urllib.error.HTTPError)
            else {"status": "failed", "error_type": type(exc).__name__, "failure_category": "transport_failure"}
        )
        store.write(
            "direct_deepseek_canary_transport",
            reservation,
            diagnostic,
        )
        print("direct canary transport failure; reservation retained", file=sys.stderr)
        return 1

    latency = time.perf_counter() - start
    choice = (payload.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    tool_calls = message.get("tool_calls") or []
    parsed_arguments: Any = None
    args_valid = False
    if len(tool_calls) == 1:
        try:
            parsed_arguments = json.loads(tool_calls[0]["function"]["arguments"])
            args_valid = parsed_arguments == {"status": "ok"}
        except (KeyError, TypeError, json.JSONDecodeError):
            pass
    usage = payload.get("usage") or {}
    details = usage.get("completion_tokens_details") or {}
    reasoning_tokens = int(details.get("reasoning_tokens") or usage.get("reasoning_tokens") or 0)
    reasoning_content = message.get("reasoning_content")
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    returned_cost = usage.get("cost")
    actual_cost = (
        float(returned_cost)
        if returned_cost is not None
        else (prompt_tokens * PROMPT_USD_PER_MILLION + completion_tokens * COMPLETION_USD_PER_MILLION) / 1_000_000
    )
    try:
        ledger.settle(reservation, actual_cost)
    except Exception as exc:
        store.write("direct_deepseek_canary_budget", reservation, {"status": "overrun", "error_type": type(exc).__name__})
        print("direct canary budget failure", file=sys.stderr)
        return 1
    valid = {
        "http_status": status == 200,
        "model_identity": payload.get("model") == MODEL,
        "finish_reason": choice.get("finish_reason") == "tool_calls",
        "one_valid_tool_call": args_valid,
        "zero_reasoning_tokens": reasoning_tokens == 0,
        "no_reasoning_content": not reasoning_content,
        "structured_output_requested": True,
    }
    store.write(
        "direct_deepseek_canary",
        reservation,
        {
            "route": {"base_url": "https://api.deepseek.com", "model": MODEL, "model_fallback": False, "reasoning_effort": "none"},
            "http_status": status,
            "response_model": payload.get("model"),
            "finish_reason": choice.get("finish_reason"),
            "tool_call_count": len(tool_calls),
            "tool_name": ((tool_calls[0].get("function") or {}).get("name") if len(tool_calls) == 1 else None),
            "parsed_tool_arguments": parsed_arguments,
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "total_tokens": int(usage.get("total_tokens") or 0), "reasoning_tokens": reasoning_tokens},
            "reasoning_content_present": bool(reasoning_content),
            "latency_seconds": latency,
            "actual_usd": actual_cost,
            "cost_source": "provider_usage_cost" if returned_cost is not None else "published_tariff_x_response_usage",
            "request_id": request_id,
            "response_header_policy": "request-id allow-list only; authentication and sensitive headers excluded",
            "validation": valid,
        },
    )
    print(json.dumps({"reservation": reservation, "passed": all(valid.values())}))
    return 0 if all(valid.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
