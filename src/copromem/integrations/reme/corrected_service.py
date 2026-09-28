#!/usr/bin/env python3
"""Run the pinned legacy ReMe AppWorld service on locked OpenRouter clients.

The benchmark's pinned ``appworld_react_agent.py`` calls the HTTP routes in
``reme/config/service.yaml`` (including add/record/delete task memory).  This
launcher selects that source-declared service rather than the later
``reme_ai/config/default.yaml`` compatibility service, whose route set differs.
Only the OpenAI client construction is adapted to the frozen providers.
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys
import types
from typing import Any

from .transport import (
    AppendOnlyLedger,
    LockedEmbeddingOpenAI,
    LockedOpenAI,
)


ROOT = pathlib.Path("/mnt/e/Project/AAMAS/COPROMEM")
SOURCE = pathlib.Path("/home/xiqhq/copromem-reme")


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("'\"")
    return values


class LockedAsyncOpenAI:
    """Async façade retaining upstream streaming interface over one locked call."""
    def __init__(self, **kwargs: Any) -> None:
        self._sync = LockedOpenAI(**kwargs)

        async def create(**params: Any) -> Any:
            result = self._sync.chat.completions.create(**params)
            if not params.get("stream"):
                return result

            async def chunks() -> Any:
                for chunk in result:
                    yield chunk
            return chunks()

        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=create))

    async def close(self) -> None:
        return None


class LockedAsyncEmbeddingOpenAI:
    """Async embedding façade; it exposes no generative chat operation."""
    def __init__(self, **kwargs: Any) -> None:
        self._sync = LockedEmbeddingOpenAI(**kwargs)

        async def create(**params: Any) -> Any:
            return self._sync.embeddings.create(**params)

        self.embeddings = types.SimpleNamespace(create=create)

    async def close(self) -> None:
        return None


def main() -> None:
    values = load_env()
    if not values.get("OPENROUTER_API_KEY"):
        raise RuntimeError("locked OpenRouter credential is absent")
    if str(SOURCE) not in sys.path:
        sys.path.insert(0, str(SOURCE))
    port = int(os.environ["OFFICIAL_REME_PORT"])
    run_dir = pathlib.Path(os.environ["OFFICIAL_REME_RUN_DIR"])
    progress = pathlib.Path(os.environ["OFFICIAL_REME_PROGRESS"])
    service_name = os.environ["OFFICIAL_REME_SERVICE_NAME"]
    ledger = AppendOnlyLedger(pathlib.Path(os.environ["OFFICIAL_REME_LEDGER"]),
                              float(os.environ["OFFICIAL_PILOT_HARD_CAP"]))

    # Patch precisely the two source modules that instantiate OpenAI clients;
    # the source's prompts, HTTP schemas, vector-store calls and algorithms are
    # otherwise executed unchanged.
    import reme.core.llm.openai_llm as upstream_llm
    import reme.core.embedding.openai_embedding_model as upstream_embedding
    upstream_llm.AsyncOpenAI = lambda **_: LockedAsyncOpenAI(
        api_key=values["OPENROUTER_API_KEY"], ledger=ledger, progress=progress,
        role=f"reme_lifecycle:{service_name}",
    )
    upstream_embedding.AsyncOpenAI = lambda **_: LockedAsyncEmbeddingOpenAI(
        api_key=values["OPENROUTER_API_KEY"], base_url="https://openrouter.ai/api/v1",
        ledger=ledger, progress=progress, role=f"reme_embedding:{service_name}",
        allowed_model="openai/text-embedding-3-small", provider="azure",
        provider_only="azure", usd_per_input_token=0.02 / 1_000_000,
    )
    from reme.reme import ReMe
    app = ReMe(
        "backend=http", f"http.port={port}", "vector_store.default.backend=memory",
        "llms.default.model_name=deepseek/deepseek-v4.1-flash",
        "embedding_models.default.model_name=openai/text-embedding-3-small",
        "embedding_models.default.dimensions=1024",
        llm_api_key="locked", llm_base_url="https://openrouter.ai/api/v1",
        embedding_api_key="locked", embedding_base_url="https://openrouter.ai/api/v1",
        working_dir=str(run_dir), config_path="service", enable_logo=False,
        log_to_console=False,
    )
    app.run_service()


if __name__ == "__main__":
    main()
