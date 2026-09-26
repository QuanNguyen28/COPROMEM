#!/usr/bin/env python3
"""Start the pinned ReMe HTTP service with only its LLM transport adapted."""
from __future__ import annotations

import asyncio
import os
import pathlib
import types

from research.official_pilot.locked_openrouter import AppendOnlyLedger, LockedEmbeddingOpenAI, LockedOpenAI

ROOT = pathlib.Path("/mnt/e/Project/AAMAS/COPROMEM")


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("'\"")
    return values


class LockedAsyncOpenAI:
    """Async SDK facade over the one locked non-streaming request path."""
    def __init__(self, *args: object, **kwargs: object) -> None:
        self._sync = LockedOpenAI(*args, **kwargs)
        async def create(**params: object):
            result = self._sync.chat.completions.create(**params)
            if not params.get("stream"):
                return result
            async def chunks():
                for chunk in result:
                    yield chunk
            return chunks()
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=create))


def main() -> None:
    values = load_env()
    required = ("OPENROUTER_API_KEY",)
    if any(not values.get(key) for key in required):
        raise RuntimeError("required local route configuration is absent")
    port = int(os.environ["OFFICIAL_REME_PORT"])
    run_dir = pathlib.Path(os.environ["OFFICIAL_REME_RUN_DIR"])
    progress = pathlib.Path(os.environ["OFFICIAL_REME_PROGRESS"])
    ledger_path = pathlib.Path(os.environ.get("OFFICIAL_REME_LEDGER", str(run_dir / "ledger.jsonl")))
    ledger = AppendOnlyLedger(ledger_path, 35.0)

    # These are transport boundaries only.  The pinned upstream algorithms,
    # prompts, request contents and vector-store lifecycle remain unchanged.
    import flowllm.core.llm.openai_compatible_llm as flow_llm
    flow_llm.OpenAI = lambda **_: LockedOpenAI(api_key=values["OPENROUTER_API_KEY"], ledger=ledger,
        progress=progress, role="reme_lifecycle")
    flow_llm.AsyncOpenAI = lambda **_: LockedAsyncOpenAI(api_key=values["OPENROUTER_API_KEY"], ledger=ledger,
        progress=progress, role="reme_lifecycle")

    import flowllm.core.embedding_model.openai_compatible_embedding_model as flow_embedding
    flow_embedding.OpenAI = lambda **_: LockedEmbeddingOpenAI(
        api_key=values["OPENROUTER_API_KEY"], base_url="https://openrouter.ai/api/v1",
        ledger=ledger, progress=progress, role="reme_embedding",
        allowed_model="openai/text-embedding-3-small", provider="azure", provider_only="azure",
        usd_per_input_token=0.02 / 1_000_000)

    from reme_ai.main import ReMeApp
    with ReMeApp(
        "backend=http", f"http.port={port}",
        "llm.default.model_name=deepseek/deepseek-v4.1-flash",
        "embedding_model.default.model_name=openai/text-embedding-3-small",
        "vector_store.default.backend=memory",
    ) as app:
        app.run_service()


if __name__ == "__main__":
    main()
