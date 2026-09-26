"""One-shot, fail-closed Hive Models tool-calling canary."""

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
from copromem.direct_deepseek_transport import sanitized_request_id
from copromem.hive_transport import (
    HIVE_CANARY_RESERVATION_USD,
    HIVE_CHAT_COMPLETIONS_URL,
    HIVE_MODEL,
    hive_tool_canary_body,
    sanitize_hive_http_error,
)
from copromem.providers import BudgetLedger


ROOT = Path("artifacts/research/reme_copromem_comparison/openrouter_brokered_smoke")


def dotenv_key(path: Path) -> str | None:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("HIVE_API_KEY="):
            value = line.split("=", 1)[1].strip().strip("\"'")
            return value or None
    return None


def model_is_consistent(value: object) -> bool:
    return isinstance(value, str) and value.lower().replace("_", "-") == HIVE_MODEL


def main() -> int:
    key = os.environ.get("HIVE_API_KEY") or dotenv_key(Path(".env"))
    if not key:
        print("HIVE_API_KEY unavailable; no request sent", file=sys.stderr)
        return 2
    store = RunStore(ROOT)
    ledger = BudgetLedger(store, max_usd=1.0, max_attempts=78)
    reservation = ledger.reserve(HIVE_CANARY_RESERVATION_USD)
    store.write(
        "hive_canary_role",
        reservation,
        {
            "role": "hive_models_strict_tool_canary",
            "endpoint": HIVE_CHAT_COMPLETIONS_URL,
            "provider": "hive_models",
            "model": HIVE_MODEL,
            "stream": False,
            "retries": 0,
            "fallback": False,
            "reasoning_mode": "not_requested",
            "reservation_usd": HIVE_CANARY_RESERVATION_USD,
        },
    )
    request = urllib.request.Request(
        HIVE_CHAT_COMPLETIONS_URL,
        data=json.dumps(hive_tool_canary_body()).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
            request_id = sanitized_request_id(response.headers)
            status = response.status
    except urllib.error.HTTPError as exc:
        store.write("hive_canary_transport", reservation, sanitize_hive_http_error(exc))
        print("Hive canary HTTP failure; reservation retained", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        store.write(
            "hive_canary_transport",
            reservation,
            {"status": "failed", "provider": "hive_models", "failure_category": "transport_failure", "error_type": type(exc).__name__},
        )
        print("Hive canary transport failure; reservation retained", file=sys.stderr)
        return 1

    choice = (payload.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    tool_calls = message.get("tool_calls") or []
    parsed: Any = None
    valid_args = False
    if len(tool_calls) == 1:
        try:
            parsed = json.loads(tool_calls[0]["function"]["arguments"])
            valid_args = parsed == {"status": "ok"}
        except (KeyError, TypeError, json.JSONDecodeError):
            pass
    usage = payload.get("usage") or {}
    reasoning_tokens = int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or usage.get("reasoning_tokens") or 0)
    reasoning_content = message.get("reasoning_content")
    provider_cost = usage.get("cost")
    if provider_cost is not None:
        ledger.settle(reservation, float(provider_cost))
    valid = {
        "http_success": status == 200,
        "model_identity": model_is_consistent(payload.get("model")),
        "one_valid_tool_call": valid_args,
        "no_reasoning_content": not reasoning_content,
        "zero_reasoning_tokens": reasoning_tokens == 0,
        "sanitized_request_id": request_id is not None,
    }
    store.write(
        "hive_canary",
        reservation,
        {
            "endpoint": HIVE_CHAT_COMPLETIONS_URL,
            "provider": "hive_models",
            "requested_model": HIVE_MODEL,
            "response_model": payload.get("model"),
            "http_status": status,
            "finish_reason": choice.get("finish_reason"),
            "tool_call_count": len(tool_calls),
            "tool_name": ((tool_calls[0].get("function") or {}).get("name") if len(tool_calls) == 1 else None),
            "parsed_tool_arguments": parsed,
            "usage": {"prompt_tokens": int(usage.get("prompt_tokens") or 0), "completion_tokens": int(usage.get("completion_tokens") or 0), "total_tokens": int(usage.get("total_tokens") or 0), "reasoning_tokens": reasoning_tokens},
            "latency_seconds": time.perf_counter() - started,
            "request_id": request_id,
            "actual_cost_usd": float(provider_cost) if provider_cost is not None else None,
            "cost_status": "provider_reported" if provider_cost is not None else "not_available; reservation retained",
            "validation": valid,
        },
    )
    print(json.dumps({"reservation": reservation, "passed": all(valid.values())}))
    return 0 if all(valid.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
