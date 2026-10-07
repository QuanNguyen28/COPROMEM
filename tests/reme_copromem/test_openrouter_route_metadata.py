import json
import http.client
import hashlib
import io
import urllib.error

import pytest

from copromem.integrations.reme import transport


class _Response:
    status = 200
    headers = {"content-type": "application/json", "x-request-id": "request-test"}

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def _payload(*, provider="DeepInfra", model=transport.MODEL, reasoning=0):
    return {
        "id": "generation-test",
        "model": model,
        "openrouter_metadata": {
            "endpoints": {
                "available": [{"model": model, "provider": provider, "selected": True}],
                "total": 1,
            },
            "requested": transport.MODEL,
        },
        "choices": [{"finish_reason": "stop", "message": {"content": "ok"}}],
        "usage": {"prompt_tokens": 2, "completion_tokens": 1, "cost": 0.000001,
                  "completion_tokens_details": {"reasoning_tokens": reasoning}},
    }


def _client(tmp_path):
    ledger = transport.AppendOnlyLedger(tmp_path / "ledger.jsonl", 1.0)
    return transport.LockedChatCompletions("secret", ledger, tmp_path / "progress.jsonl", "executor:test"), ledger


def test_current_openrouter_metadata_is_required_and_provider_is_selected(monkeypatch, tmp_path):
    seen = {}

    def urlopen(request, timeout):
        seen["metadata_header"] = request.get_header("X-openrouter-metadata")
        return _Response(_payload())

    monkeypatch.setattr(transport, "count_chat_tokens", lambda *_: 10)
    monkeypatch.setattr(transport.urllib.request, "urlopen", urlopen)
    client, _ = _client(tmp_path)
    result = client.create(model=transport.MODEL, messages=[{"role": "user", "content": "x"}])

    assert seen["metadata_header"] == "enabled"
    assert result.model == transport.MODEL
    assert client.last_record["provider"] == transport.PROVIDER
    assert client.last_record["provider_evidence"] == "openrouter_metadata.selected_endpoint"
    progress = [json.loads(line) for line in (tmp_path / "progress.jsonl").read_text().splitlines()]
    assert progress[-1]["event"] == "call_settled"
    assert progress[-1]["provider_evidence"] == "openrouter_metadata.selected_endpoint"


def test_legacy_top_level_provider_remains_supported(monkeypatch, tmp_path):
    payload = _payload()
    payload.pop("openrouter_metadata")
    payload["provider"] = "DeepInfra"
    monkeypatch.setattr(transport, "count_chat_tokens", lambda *_: 10)
    monkeypatch.setattr(transport.urllib.request, "urlopen", lambda *_args, **_kwargs: _Response(payload))
    client, _ = _client(tmp_path)

    client.create(model=transport.MODEL, messages=[{"role": "user", "content": "x"}])
    assert client.last_record["provider_evidence"] == "legacy_top_level"


def test_route_rejection_is_diagnostic_and_ledger_settled(monkeypatch, tmp_path):
    monkeypatch.setattr(transport, "count_chat_tokens", lambda *_: 10)
    monkeypatch.setattr(transport.urllib.request, "urlopen",
                        lambda *_args, **_kwargs: _Response(_payload(provider="Other", reasoning=3)))
    client, _ = _client(tmp_path)

    with pytest.raises(transport.DispatchFailure):
        client.create(model=transport.MODEL, messages=[{"role": "user", "content": "x"}])

    ledger = [json.loads(line) for line in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert [row["event"] for row in ledger] == ["reserve", "settle"]
    assert ledger[-1]["outcome"] == "route_rejected"
    progress = [json.loads(line) for line in (tmp_path / "progress.jsonl").read_text().splitlines()]
    rejected = progress[-1]
    assert rejected["rejection_reasons"] == ["provider", "reasoning_tokens"]
    assert rejected["resolved_provider"] == "other"
    assert rejected["reasoning_tokens"] == 3


def test_ambiguous_selected_endpoints_fail_closed(monkeypatch, tmp_path):
    payload = _payload()
    payload["openrouter_metadata"]["endpoints"]["available"].append(
        {"model": transport.MODEL, "provider": "DeepSeek", "selected": True})
    monkeypatch.setattr(transport, "count_chat_tokens", lambda *_: 10)
    monkeypatch.setattr(transport.urllib.request, "urlopen", lambda *_args, **_kwargs: _Response(payload))
    client, _ = _client(tmp_path)

    with pytest.raises(transport.DispatchFailure):
        client.create(model=transport.MODEL, messages=[{"role": "user", "content": "x"}])
    rejected = json.loads((tmp_path / "progress.jsonl").read_text().splitlines()[-1])
    assert rejected["rejection_reasons"] == ["provider"]
    assert rejected["provider_evidence"] == "absent"


def test_non_json_response_records_only_sanitized_transport_evidence(monkeypatch, tmp_path):
    response = _Response({})
    response.payload = None
    response.read = lambda: b"not-json-and-never-persisted"
    response.headers = {"content-type": "text/html; charset=utf-8", "x-request-id": "safe-id"}
    monkeypatch.setattr(transport, "count_chat_tokens", lambda *_: 10)
    monkeypatch.setattr(transport.urllib.request, "urlopen", lambda *_args, **_kwargs: response)
    client, _ = _client(tmp_path)

    with pytest.raises(transport.DispatchFailure, match="non-JSON"):
        client.create(model=transport.MODEL, messages=[{"role": "user", "content": "x"}])

    progress = json.loads((tmp_path / "progress.jsonl").read_text().splitlines()[-1])
    assert progress["event"] == "call_response_invalid"
    assert progress["http_status"] == 200
    assert progress["content_type"] == "text/html"
    assert progress["request_id"] == "safe-id"
    assert progress["response_length"] == len(b"not-json-and-never-persisted")
    assert "not-json" not in json.dumps(progress)


def test_incomplete_read_settles_unknown_transport_outcome_conservatively(monkeypatch, tmp_path):
    monkeypatch.setattr(transport, "count_chat_tokens", lambda *_: 10)
    monkeypatch.setattr(transport.urllib.request, "urlopen",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(http.client.IncompleteRead(b"", 1)))
    client, _ = _client(tmp_path)
    with pytest.raises(transport.DispatchFailure, match="locked OpenRouter request failed"):
        client.create(model=transport.MODEL, messages=[{"role": "user", "content": "x"}])
    ledger = [json.loads(line) for line in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert [row["event"] for row in ledger] == ["reserve", "settle"]
    assert ledger[-1]["outcome"] == "transport_outcome_unknown_conservative_bound"
    assert ledger[-1]["charge_status"] == "unknown_conservative_bound"
    assert ledger[-1]["usd"] == ledger[0]["usd"]
    progress = json.loads((tmp_path / "progress.jsonl").read_text().splitlines()[-1])
    assert progress["event"] == "call_failed"
    assert progress["charge_status"] == "unknown_conservative_bound"


def test_http_error_records_only_sanitized_transport_metadata(monkeypatch, tmp_path):
    error_body = b'{"error":"provider response must never be written to progress"}'
    headers = {"content-type": "application/json; charset=utf-8", "x-request-id": "safe-request-id"}
    error = urllib.error.HTTPError("https://openrouter.ai/api/v1/chat/completions", 503,
                                   "Service Unavailable", headers, io.BytesIO(error_body))
    monkeypatch.setattr(transport, "count_chat_tokens", lambda *_: 10)
    monkeypatch.setattr(transport.urllib.request, "urlopen",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(error))
    client, _ = _client(tmp_path)

    with pytest.raises(transport.DispatchFailure, match="locked OpenRouter request failed"):
        client.create(model=transport.MODEL, messages=[{"role": "user", "content": "x"}])

    ledger = [json.loads(line) for line in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert [row["event"] for row in ledger] == ["reserve", "settle"]
    assert ledger[-1]["outcome"] == "transport_outcome_unknown_conservative_bound"
    assert ledger[-1]["usd"] == ledger[0]["usd"]
    progress_text = (tmp_path / "progress.jsonl").read_text()
    progress = json.loads(progress_text)
    assert progress["event"] == "call_failed"
    assert progress["error_type"] == "HTTPError"
    assert progress["http_status"] == 503
    assert progress["content_type"] == "application/json"
    assert progress["request_id"] == "safe-request-id"
    assert progress["response_bytes_read"] == len(error_body)
    assert progress["response_sha256"] == hashlib.sha256(error_body).hexdigest()
    assert error_body.decode() not in progress_text


def test_explicit_429_retries_same_reserved_logical_call(monkeypatch, tmp_path):
    """429 is retried in-place; it must not create a second ledger reserve."""
    error = urllib.error.HTTPError(
        "https://openrouter.ai/api/v1/chat/completions", 429, "Too Many Requests",
        {"retry-after": "0", "content-type": "application/json"}, io.BytesIO(b"never persist me"))
    responses = [error, _Response(_payload())]
    sleeps = []

    def urlopen(*_args, **_kwargs):
        item = responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    monkeypatch.setattr(transport, "count_chat_tokens", lambda *_: 10)
    monkeypatch.setattr(transport, "HTTP_429_MAX_RETRIES", 1)
    monkeypatch.setattr(transport, "HTTP_429_INITIAL_BACKOFF_SECONDS", 0.0)
    monkeypatch.setattr(transport, "HTTP_429_MAX_BACKOFF_SECONDS", 0.0)
    monkeypatch.setattr(transport.time, "sleep", sleeps.append)
    monkeypatch.setattr(transport.urllib.request, "urlopen", urlopen)
    client, _ = _client(tmp_path)

    result = client.create(model=transport.MODEL, messages=[{"role": "user", "content": "x"}])

    assert result.model == transport.MODEL
    assert sleeps == [0.0]
    ledger = [json.loads(line) for line in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert [row["event"] for row in ledger] == ["reserve", "settle"]
    progress_text = (tmp_path / "progress.jsonl").read_text()
    progress = [json.loads(line) for line in progress_text.splitlines()]
    assert progress[0] == {"event": "call_rate_limited_retry", "id": progress[0]["id"],
                           "role": "executor:test", "http_status": 429,
                           "retry_attempt": 1, "retry_delay_seconds": 0.0}
    assert progress[-1]["event"] == "call_settled"
    assert "never persist me" not in progress_text


def test_exhausted_429_retries_preserve_conservative_terminal_accounting(monkeypatch, tmp_path):
    def urlopen(*_args, **_kwargs):
        raise urllib.error.HTTPError("https://openrouter.ai/api/v1/chat/completions", 429,
                                     "Too Many Requests", {}, io.BytesIO(b"private provider body"))

    monkeypatch.setattr(transport, "count_chat_tokens", lambda *_: 10)
    monkeypatch.setattr(transport, "HTTP_429_MAX_RETRIES", 1)
    monkeypatch.setattr(transport, "HTTP_429_INITIAL_BACKOFF_SECONDS", 0.0)
    monkeypatch.setattr(transport, "HTTP_429_MAX_BACKOFF_SECONDS", 0.0)
    monkeypatch.setattr(transport.time, "sleep", lambda _delay: None)
    monkeypatch.setattr(transport.urllib.request, "urlopen", urlopen)
    client, _ = _client(tmp_path)

    with pytest.raises(transport.DispatchFailure, match="locked OpenRouter request failed"):
        client.create(model=transport.MODEL, messages=[{"role": "user", "content": "x"}])

    ledger = [json.loads(line) for line in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert [row["event"] for row in ledger] == ["reserve", "settle"]
    progress_text = (tmp_path / "progress.jsonl").read_text()
    assert [json.loads(line)["event"] for line in progress_text.splitlines()] == ["call_rate_limited_retry", "call_failed"]
    assert "private provider body" not in progress_text


def test_public_route_preflight_accepts_only_healthy_exact_provider(monkeypatch):
    payload = {"data": {"endpoints": [
        {"name": "Other | model", "provider_name": "Other", "status": 0},
        {"name": "DeepInfra | model", "provider_name": "DeepInfra", "status": 0},
    ]}}
    monkeypatch.setattr(transport.urllib.request, "urlopen",
                        lambda *_args, **_kwargs: _Response(payload))
    record = transport.verify_locked_chat_route_available()
    assert record == {"model": transport.MODEL, "provider": transport.PROVIDER,
                      "status": 0, "endpoint_name": "DeepInfra | model"}


@pytest.mark.parametrize("status", [-5, -2, 1, None, "bad"])
def test_public_route_preflight_rejects_unhealthy_or_malformed_status(monkeypatch, status):
    payload = {"data": {"endpoints": [
        {"name": "DeepInfra | model", "provider_name": "DeepInfra", "status": status},
    ]}}
    monkeypatch.setattr(transport.urllib.request, "urlopen",
                        lambda *_args, **_kwargs: _Response(payload))
    with pytest.raises(transport.DispatchFailure):
        transport.verify_locked_chat_route_available()
