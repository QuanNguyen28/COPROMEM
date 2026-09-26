"""Provider-neutral validation for native-tool transport records."""
from __future__ import annotations

from typing import Mapping, Any


def is_completion_truncation(record: Mapping[str, Any], *, max_tokens: int) -> bool:
    tokens = record.get("tokens", {})
    return (record.get("finish_reason") == "length" and tokens.get("completion") == max_tokens
            and record.get("response_model") == "deepseek-flash")


def bounded_native_feedback(native_reply: Mapping[str, Any], *, max_chars: int = 3000) -> str:
    """Bound conversation growth without changing any native action or result."""
    import json
    return json.dumps(native_reply, sort_keys=True)[:max_chars]
