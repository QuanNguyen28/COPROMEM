#!/usr/bin/env python3
"""Deterministic no-network verifier for the official ReMe transport adapter."""
from __future__ import annotations

import json
import pathlib
import tempfile

from research.official_pilot.locked_openrouter import AppendOnlyLedger, LockedOpenAI
import research.official_pilot.locked_openrouter as transport


class Response:
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def read(self):
        return json.dumps({"model": "deepseek/deepseek-v4.1-flash", "provider": "deepseek",
            "choices": [{"message": {"content": "```python\nx=1\n```"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 5, "cost": 0.00001,
                      "completion_tokens_details": {"reasoning_tokens": 0}}}).encode()


def main() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = pathlib.Path(temp)
        old = transport.urllib.request.urlopen
        transport.urllib.request.urlopen = lambda *_args, **_kwargs: Response()
        try:
            client = LockedOpenAI(api_key="fixture", ledger=AppendOnlyLedger(root / "ledger.jsonl", 1.0),
                                  progress=root / "progress.jsonl", role="fixture")
            reply = client.chat.completions.create(model="deepseek/deepseek-v4.1-flash",
                messages=[{"role": "user", "content": "x"}], stream=False)
            chunks = list(client.chat.completions.create(model="deepseek/deepseek-v4.1-flash",
                messages=[{"role": "user", "content": "x"}], stream=True))
        finally:
            transport.urllib.request.urlopen = old
        assert reply.choices[0].message.content == "```python\nx=1\n```"
        assert len(chunks) == 2 and chunks[0].choices[0].delta.content
        lines = (root / "ledger.jsonl").read_text().splitlines()
        assert sum(json.loads(line)["event"] == "reserve" for line in lines) == 2
        assert sum(json.loads(line)["event"] == "settle" for line in lines) == 2
    print("locked_transport_mock=passed")


if __name__ == "__main__":
    main()
