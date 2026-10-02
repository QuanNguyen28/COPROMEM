import json
from pathlib import Path

import pytest

from scripts import run_v622_parallel_baseline_pilot as pilot


def test_parallel_pilot_binds_the_manifest_label_to_its_frozen_protocol_record(tmp_path: Path):
    (tmp_path / "engineering-protocol.json").write_text(
        json.dumps({"version": "v6.2.2-parallel-baseline-pilot-protocol-v99-fixture"}), encoding="utf-8"
    )
    assert pilot._declared_protocol(tmp_path) == "v6.2.2-parallel-baseline-pilot-protocol-v99-fixture"


def test_parallel_pilot_rejects_a_missing_or_wrong_protocol_version(tmp_path: Path):
    with pytest.raises(RuntimeError, match="readable versioned"):
        pilot._declared_protocol(tmp_path)
    (tmp_path / "engineering-protocol.json").write_text(json.dumps({"version": "other"}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="protocol version is invalid"):
        pilot._declared_protocol(tmp_path)
