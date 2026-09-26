import io
import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from urllib.error import HTTPError

import pytest

from copromem.direct_deepseek_transport import sanitize_http_error, sanitized_request_id


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (400, "invalid_model_or_parameters"),
        (401, "invalid_credentials"),
        (402, "insufficient_balance"),
        (404, "invalid_model_or_parameters"),
        (422, "invalid_model_or_parameters"),
        (429, "rate_limited"),
        (503, "server_failure"),
    ],
)
def test_sanitizes_documented_http_failure_categories(status, expected):
    payload = {"error": {"code": "invalid_parameter", "type": "invalid_request_error", "message": "Bearer sk-secret must not persist"}}
    error = HTTPError(
        "https://api.deepseek.com/chat/completions",
        status,
        "failure",
        {"X-Request-ID": "req_fixture", "Authorization": "Bearer sk-secret"},
        io.BytesIO(json.dumps(payload).encode()),
    )
    record = sanitize_http_error(error)
    assert record["http_status"] == status
    assert record["failure_category"] == expected
    assert record["request_id"] == "req_fixture"
    assert "sk-secret" not in record["error_message"]
    assert record["deepseek_error_code"] == "invalid_parameter"


def test_unparseable_error_body_is_safe():
    error = HTTPError("https://api.deepseek.com", 500, "failure", {}, io.BytesIO(b"not-json"))
    record = sanitize_http_error(error)
    assert record["failure_category"] == "server_failure"
    assert record["error_message"] == "no safely parseable provider message"


def test_success_header_allow_list_keeps_only_request_id():
    assert sanitized_request_id({"Authorization": "Bearer secret", "X-Request-ID": "req_safe"}) == "req_safe"


def test_direct_canary_body_is_non_streaming_strict_and_has_no_response_format():
    spec = spec_from_file_location("direct_deepseek_canary", Path("scripts/direct_deepseek_canary.py"))
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    # The production body is intentionally built locally inside main; guard the
    # stable source-level transport contract without touching credentials.
    source = Path("scripts/direct_deepseek_canary.py").read_text(encoding="utf-8")
    assert '"stream": False' in source
    assert '"max_tokens": 128' in source
    assert '"strict": True' in source
    assert '"response_format"' not in source


def test_redacts_masked_key_suffix_and_recovers_request_id_from_message():
    payload = {"error": {"message": "Authentication Fails, Your api key: ****Sw== is invalid (request_id: req_from_body)"}}
    error = HTTPError("https://api.deepseek.com", 401, "failure", {}, io.BytesIO(json.dumps(payload).encode()))
    record = sanitize_http_error(error)
    assert "Sw==" not in record["error_message"]
    assert record["request_id"] == "req_from_body"
