"""ReasoningBank adapter for the maintained Azure/OpenRouter embedding boundary.

This module deliberately contains no HTTP, normalization, batching, pricing,
retry, or provider-validation implementation.  Those are owned by ReMe's
maintained ``LockedEmbeddings`` transport so controlled-baseline arms cannot
drift at the embedding boundary.
"""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ..reme.transport import AppendOnlyLedger, LockedEmbeddings


MODEL = "openai/text-embedding-3-small"
PROVIDER = "azure"
DIMENSIONS = 1024
ENCODING_FORMAT = "float"
TRANSPORT_IDENTITY = "copromem.integrations.reme.transport.LockedEmbeddings"


class SharedAzureOpenRouterEmbedder:
    """Expose a minimal task/document embedder backed by the locked transport."""

    def __init__(self, *, api_key: str, ledger: AppendOnlyLedger, progress: Path) -> None:
        self._client = LockedEmbeddings(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            ledger=ledger,
            progress=progress,
            role="reasoningbank_embedding",
            allowed_model=MODEL,
            provider=PROVIDER,
            provider_only=PROVIDER,
            usd_per_input_token=0.02 / 1_000_000,
        )

    def __call__(self, text: str, _purpose: str) -> Sequence[float]:
        response = self._client.create(
            model=MODEL, input=text, dimensions=DIMENSIONS,
            encoding_format=ENCODING_FORMAT,
        )
        if len(response.data) != 1:
            raise RuntimeError("ReasoningBank embedding response cardinality mismatch")
        vector = getattr(response.data[0], "embedding", None)
        if not isinstance(vector, list) or len(vector) != DIMENSIONS:
            raise RuntimeError("ReasoningBank embedding dimension mismatch")
        return tuple(float(value) for value in vector)
