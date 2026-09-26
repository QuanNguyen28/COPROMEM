"""Sanitized diagnostics for the direct DeepSeek transport."""

from __future__ import annotations

import json
import re
from typing import Any


_SENSITIVE_HEADERS = {"authorization", "proxy-authorization", "cookie", "set-cookie"}
_REQUEST_IDS = {"x-request-id", "request-id", "x-deepseek-request-id"}


def failure_category(status: int) -> str:
    if status == 401:
        return "invalid_credentials"
    if status == 402:
        return "insufficient_balance"
    if status in {400, 404, 422}:
        return "invalid_model_or_parameters"
    if status == 429:
        return "rate_limited"
    if 500 <= status <= 599:
        return "server_failure"
    return "request_failure"


def _redact_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = re.sub(r"(?i)(bearer\s+|api\s*[_-]?\s*key\s*[:=]\s*)[^\s,;]+", r"\1[REDACTED]", value)
    value = re.sub(r"sk-[A-Za-z0-9_-]+", "[REDACTED]", value)
    return value[:512]


def sanitize_http_error(exc: Any) -> dict[str, Any]:
    """Extract only an allow-listed, safely redacted error diagnostic."""
    status = int(exc.code)
    headers = getattr(exc, "headers", None) or {}
    request_id = next(
        (str(value) for name, value in headers.items() if str(name).lower() in _REQUEST_IDS),
        None,
    )
    raw = ""
    try:
        raw = exc.read().decode("utf-8", errors="replace")[:4096]
        body = json.loads(raw)
    except (AttributeError, OSError, UnicodeError, json.JSONDecodeError):
        body = {}
    error = body.get("error") if isinstance(body, dict) else {}
    error = error if isinstance(error, dict) else {}
    message = _redact_text(error.get("message")) or "no safely parseable provider message"
    if request_id is None:
        match = re.search(r"(?i)request_id\s*:\s*([A-Za-z0-9._-]+)", message)
        request_id = match.group(1) if match else None
    return {
        "status": "failed",
        "http_status": status,
        "failure_category": failure_category(status),
        "deepseek_error_code": _redact_text(error.get("code")),
        "deepseek_error_type": _redact_text(error.get("type")),
        "request_id": request_id,
        "error_message": message,
        "error_type": type(exc).__name__,
        "response_header_policy": "request-id allow-list only; authentication and sensitive headers excluded",
    }


def sanitized_request_id(headers: Any) -> str | None:
    """Return the sole response header retained for a successful request."""
    return next(
        (str(value) for name, value in headers.items() if str(name).lower() in _REQUEST_IDS),
        None,
    )
