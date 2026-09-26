"""Pinned, zero-secret configuration and diagnostics for Hive LLM transport."""

from __future__ import annotations

from typing import Any

from .direct_deepseek_transport import sanitize_http_error

HIVE_CHAT_COMPLETIONS_URL = "https://api-cdn.thehive.ai/api/v3/chat/completions"
HIVE_MODEL = "deepseek-ai/deepseek-v4.1-flash"
HIVE_CANARY_RESERVATION_USD = 0.01


def hive_failure_category(status: int) -> str:
    if status == 401:
        return "invalid_credentials"
    if status in {402, 405}:
        return "insufficient_balance"
    if status in {400, 404, 422}:
        return "invalid_model_or_parameters"
    if status == 429:
        return "rate_limited"
    if 500 <= status <= 599:
        return "server_failure"
    return "request_failure"


def sanitize_hive_http_error(exc: Any) -> dict[str, Any]:
    record = sanitize_http_error(exc)
    record["failure_category"] = hive_failure_category(record["http_status"])
    record["provider"] = "hive_models"
    return record


def hive_tool_canary_body() -> dict[str, Any]:
    """Return a secret-free, exact-model request shape; never dispatches."""
    schema = {
        "type": "object",
        "properties": {"status": {"type": "string", "enum": ["ok"]}},
        "required": ["status"],
        "additionalProperties": False,
    }
    return {
        "model": HIVE_MODEL,
        "messages": [{"role": "user", "content": "Call the canary tool now."}],
        "stream": False,
        "max_tokens": 16,
        "temperature": 0,
        "tools": [{
            "type": "function",
            "function": {
                "name": "canary",
                "description": "Return the fixed canary status.",
                "parameters": schema,
                "strict": True,
            },
        }],
        "tool_choice": {"type": "function", "function": {"name": "canary"}},
    }
