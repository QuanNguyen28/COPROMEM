from __future__ import annotations

import json
from pathlib import Path

import pytest

from copromem.experiments.reme_copromem.public_operation_intent_registry import build, index, verify


def _write(root: Path, description: str = "Send money to a user.") -> None:
    root.mkdir()
    (root / "venmo.json").write_text(json.dumps({"paths": {"/venmo/transactions": {"post": {
        "operationId": "venmo__create_transaction", "description": description}}}}))


def test_public_intent_registry_is_content_addressed_and_value_free(tmp_path: Path) -> None:
    root = tmp_path / "openapi"; _write(root)
    record = build(root); verify(record)
    row = index(record)["apis.venmo.create_transaction"]
    assert row["description"] == "Send money to a user."
    assert row["description_tokens"] == ["money", "send", "to", "user"]
    assert "task" not in json.dumps(record).lower()


def test_public_intent_registry_rejects_tampering(tmp_path: Path) -> None:
    root = tmp_path / "openapi"; _write(root)
    record = build(root); record["operations"][0]["description"] = "Forged"
    with pytest.raises(ValueError, match="identity"):
        verify(record)
