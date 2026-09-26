import io
import json
from urllib.error import HTTPError

import pytest

from copromem.hive_transport import (
    HIVE_CHAT_COMPLETIONS_URL,
    HIVE_CANARY_RESERVATION_USD,
    HIVE_MODEL,
    hive_tool_canary_body,
    sanitize_hive_http_error,
)
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def test_hive_is_pinned_to_requested_endpoint_model_and_reservation():
    assert HIVE_CHAT_COMPLETIONS_URL == "https://api-cdn.thehive.ai/api/v3/chat/completions"
    assert HIVE_MODEL == "deepseek-ai/deepseek-v4.1-flash"
    assert HIVE_CANARY_RESERVATION_USD == 0.01
    body = hive_tool_canary_body()
    assert body["model"] == HIVE_MODEL and body["stream"] is False
    assert body["tools"][0]["function"]["strict"] is True
    assert "provider" not in body and "fallback" not in body


@pytest.mark.parametrize(
    ("status", "category"),
    [(400, "invalid_model_or_parameters"), (401, "invalid_credentials"),
     (405, "insufficient_balance"), (404, "invalid_model_or_parameters"),
     (422, "invalid_model_or_parameters"), (429, "rate_limited"),
     (503, "server_failure")],
)
def test_hive_sanitized_error_categories(status, category):
    raw = {"error": {"code": "fixture", "type": "fixture_error", "message": "api key: secret"}}
    error = HTTPError("https://api.thehive.ai", status, "failed", {"X-Request-ID": "hive_req"}, io.BytesIO(json.dumps(raw).encode()))
    record = sanitize_hive_http_error(error)
    assert record["provider"] == "hive_models"
    assert record["failure_category"] == category
    assert record["request_id"] == "hive_req"
    assert "secret" not in record["error_message"]


def test_hive_canary_accepts_only_the_exact_requested_model():
    spec = spec_from_file_location("hive_canary", Path("scripts/hive_canary.py"))
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.model_is_consistent("deepseek-ai/deepseek-v4.1-flash")
    assert not module.model_is_consistent("other/model")
