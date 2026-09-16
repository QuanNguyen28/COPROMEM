import hashlib
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "embedding_fetch",
    Path(__file__).parents[1] / "research/scripts/fetch_expel_embedding.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_small_asset_is_verified_against_git_blob_and_archived_sha256(tmp_path):
    payload = b'{"fixture":true}\n'
    path = tmp_path / "config.json"
    path.write_bytes(payload)
    metadata = {
        "size": len(payload),
        "blobId": hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest(),
    }
    record = module.verify_file(path, metadata)
    assert record["sha256"] == hashlib.sha256(payload).hexdigest()
    assert record["upstream"] == metadata


def test_large_asset_is_verified_against_lfs_sha256(tmp_path):
    payload = b"authored fixture, not real weights"
    path = tmp_path / "fixture.safetensors"
    path.write_bytes(payload)
    metadata = {
        "size": len(payload),
        "lfs": {"sha256": hashlib.sha256(payload).hexdigest()},
    }
    assert module.verify_file(path, metadata)["bytes"] == len(payload)


@pytest.mark.parametrize(
    "metadata, message",
    [
        ({"size": 999, "blobId": "bad"}, "size mismatch"),
        ({"size": 3, "blobId": "bad"}, "Git blob mismatch"),
        ({"size": 3, "lfs": {"sha256": "bad"}}, "LFS SHA256 mismatch"),
    ],
)
def test_corrupted_asset_fails_closed(tmp_path, metadata, message):
    path = tmp_path / "fixture"
    path.write_bytes(b"abc")
    with pytest.raises(ValueError, match=message):
        module.verify_file(path, metadata)


def test_download_allowlist_excludes_pickle_and_remote_python():
    assert "model.safetensors" in module.FILES
    assert all(
        not name.endswith((".bin", ".pt", ".pkl", ".py")) for name in module.FILES
    )
    assert len(module.REVISION) == 40
