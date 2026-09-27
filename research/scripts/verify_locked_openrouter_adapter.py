#!/usr/bin/env python3
"""Deterministic no-network verifier for the official ReMe transport adapter."""
from __future__ import annotations

import json
import pathlib
import tempfile

from research.official_pilot.locked_openrouter import (AppendOnlyLedger, ContextCeilingTermination,
    LockedOpenAI, TruncationTermination, count_chat_tokens)
import research.official_pilot.locked_openrouter as transport


class Response:
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def read(self):
        return json.dumps({"model": "deepseek/deepseek-v4.1-flash", "provider": "deepseek",
            "choices": [{"message": {"content": "```python\nx=1\n```"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 5, "cost": 0.00001,
                      "completion_tokens_details": {"reasoning_tokens": 0}}}).encode()


class LengthResponse(Response):
    def read(self):
        return json.dumps({"model": "deepseek/deepseek-v4.1-flash", "provider": "deepseek",
            "choices": [{"message": {"content": "truncated"}, "finish_reason": "length"}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 2048, "cost": 0.00001,
                      "completion_tokens_details": {"reasoning_tokens": 0}}}).encode()


def main() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = pathlib.Path(temp)
        old = transport.urllib.request.urlopen
        captured: list[dict] = []
        def fake(request, **_kwargs):
            captured.append(json.loads(request.data.decode()))
            return Response()
        transport.urllib.request.urlopen = fake
        try:
            client = LockedOpenAI(api_key="fixture", ledger=AppendOnlyLedger(root / "ledger.jsonl", 1.0),
                                  progress=root / "progress.jsonl", role="fixture")
            reply = client.chat.completions.create(model="deepseek/deepseek-v4.1-flash",
                messages=[{"role": "user", "content": "x"}], stream=False)
            chunks = list(client.chat.completions.create(model="deepseek/deepseek-v4.1-flash",
                messages=[{"role": "user", "content": "x"}], stream=True))
            assert captured and captured[0]["max_tokens"] == 2048
            assert captured[0]["temperature"] == 0.7 and captured[0]["top_p"] == 1.0
            assert captured[0]["provider"] == {"only": ["deepseek"], "allow_fallbacks": False,
                                                "require_parameters": True,
                                                "max_price": {"prompt": 0.30, "completion": 1.20}}
            assert count_chat_tokens([{"role":"user","content":"tokenizer evidence"}]) > 0
            old_ceiling = transport.INPUT_TOKEN_CEILING
            transport.INPUT_TOKEN_CEILING = 1
            try:
                client.chat.completions.create(model="deepseek/deepseek-v4.1-flash",
                    messages=[{"role":"user","content":"must not dispatch"}])
                raise AssertionError("context ceiling was not fail-closed")
            except ContextCeilingTermination:
                pass
            finally:
                transport.INPUT_TOKEN_CEILING = old_ceiling
            transport.urllib.request.urlopen = lambda *_args, **_kwargs: LengthResponse()
            try:
                client.chat.completions.create(model="deepseek/deepseek-v4.1-flash",
                    messages=[{"role":"user","content":"x"}])
                raise AssertionError("length response was accepted")
            except TruncationTermination:
                pass
        finally:
            transport.urllib.request.urlopen = old
        assert reply.choices[0].message.content == "```python\nx=1\n```"
        assert len(chunks) == 2 and chunks[0].choices[0].delta.content
        lines = (root / "ledger.jsonl").read_text().splitlines()
        # The length-limited reply is still a settled provider response, but
        # its content is rejected before any native action can be executed.
        assert sum(json.loads(line)["event"] == "reserve" for line in lines) == 3
        assert sum(json.loads(line)["event"] == "settle" for line in lines) == 3
    print("locked_transport_mock=passed")


if __name__ == "__main__":
    main()
