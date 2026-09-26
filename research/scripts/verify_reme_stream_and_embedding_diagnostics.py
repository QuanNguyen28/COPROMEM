#!/usr/bin/env python3
"""Offline regression checks for FlowLLM stream usage and safe diagnostics."""
from __future__ import annotations

import pathlib
import tempfile

from research.official_pilot.locked_openrouter import (AppendOnlyLedger, LockedEmbeddings,
                                                        ModelDumpNamespace, _sanitize_provider_error)


def main() -> None:
    usage = ModelDumpNamespace(prompt_tokens=3, completion_tokens=2, total_tokens=5)
    assert usage.model_dump() == {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}
    code, kind, message = _sanitize_provider_error(
        '{"error":{"code":"InvalidParameter","type":"invalid_request_error","message":"bad dimensions"}}')
    assert (code, kind, message) == ("InvalidParameter", "invalid_request_error", "bad dimensions")
    code, kind, message = _sanitize_provider_error("<html>server error</html>")
    assert code is None and kind is None and message == "provider returned non-JSON error"
    with tempfile.TemporaryDirectory() as directory:
        boundary = LockedEmbeddings(api_key="not-used", base_url="https://openrouter.ai/api/v1",
            ledger=AppendOnlyLedger(pathlib.Path(directory) / "ledger.jsonl", 1.0),
            progress=pathlib.Path(directory) / "progress.jsonl",
            allowed_model="openai/text-embedding-3-small", provider="openrouter",
            usd_per_input_token=0.02 / 1_000_000)
        assert boundary.allowed_model == "openai/text-embedding-3-small"
        assert boundary.provider == "openrouter"
    print("reme_stream_usage_and_embedding_diagnostics=passed")


if __name__ == "__main__":
    main()
