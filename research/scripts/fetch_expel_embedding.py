"""Download only pinned public ExpeL embedding assets, never remote Python/pickle."""

from __future__ import annotations

import hashlib
import json
import urllib.request
import uuid
from pathlib import Path

from copromem.checkpoints import RunStore, digest

MODEL = "sentence-transformers/all-mpnet-base-v2"
REVISION = "e8c3b32edf5434bc2275fc9bab85f82640a19130"
FILES = (
    "1_Pooling/config.json",
    "README.md",
    "config.json",
    "config_sentence_transformers.json",
    "model.safetensors",
    "modules.json",
    "sentence_bert_config.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
)


def verify_file(path: Path, metadata: dict) -> dict:
    size = path.stat().st_size
    if size != metadata["size"]:
        raise ValueError(f"size mismatch for {path.name}")
    sha256 = hashlib.sha256()
    blob = hashlib.sha1(f"blob {size}\0".encode())
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha256.update(chunk)
            blob.update(chunk)
    if "lfs" in metadata:
        if sha256.hexdigest() != metadata["lfs"]["sha256"]:
            raise ValueError(f"LFS SHA256 mismatch for {path.name}")
    elif blob.hexdigest() != metadata["blobId"]:
        raise ValueError(f"Git blob mismatch for {path.name}")
    return {"bytes": size, "sha256": sha256.hexdigest(), "upstream": metadata}


def main():
    root = Path(__file__).resolve().parents[2]
    store = RunStore(root / "artifacts/research/expel_native_probe_20260916")
    model_dir = store.root / "models" / "all-mpnet-base-v2" / REVISION
    model_dir.mkdir(parents=True, exist_ok=True)
    metadata_url = (
        f"https://huggingface.co/api/models/{MODEL}/revision/{REVISION}?blobs=true"
    )
    with urllib.request.urlopen(metadata_url, timeout=45) as response:
        metadata = json.load(response)
    if metadata["sha"] != REVISION:
        raise ValueError("remote revision mismatch")
    store.write("embedding_remote_metadata", digest(metadata), metadata)
    siblings = {entry["rfilename"]: entry for entry in metadata["siblings"]}
    if sum(siblings[name]["size"] for name in FILES) > 600_000_000:
        raise ValueError("selected public checkpoint exceeds declared download bound")
    manifest = {}
    for name in FILES:
        destination = model_dir / name
        expected = siblings[name]
        url = f"https://huggingface.co/{MODEL}/resolve/{REVISION}/{name}"
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            partial = destination.with_name(
                destination.name + ".part-" + uuid.uuid4().hex
            )
            try:
                with (
                    urllib.request.urlopen(url, timeout=45) as response,
                    partial.open("xb") as output,
                ):
                    written = 0
                    while chunk := response.read(1024 * 1024):
                        written += len(chunk)
                        if written > expected["size"]:
                            raise ValueError("download exceeds pinned file size")
                        output.write(chunk)
                verify_file(partial, expected)
                if destination.exists():
                    raise FileExistsError("refusing to replace an existing model file")
                partial.rename(destination)
            except Exception as exc:
                failure = {
                    "url": url,
                    "exception_type": type(exc).__name__,
                    "partial_path": str(partial),
                    "partial_bytes": partial.stat().st_size if partial.exists() else 0,
                    "remote_metadata": expected,
                }
                store.write("embedding_download_failures", digest(failure), failure)
                raise
        manifest[name] = {"url": url, **verify_file(destination, expected)}
        print(
            json.dumps(
                {"file": name, **{k: manifest[name][k] for k in ("bytes", "sha256")}}
            ),
            flush=True,
        )
    record = {
        "model": MODEL,
        "revision": REVISION,
        "files": manifest,
        "remote_metadata_id": digest(metadata),
        "model_directory": str(model_dir),
        "loader_policy": "Local safetensors and stock installed modules only; no remote Python, pickle or inference endpoint.",
        "paid_model_calls": 0,
    }
    key = digest(record)
    store.write("embedding_models", key, record)
    print(
        json.dumps({"manifest_id": key, "model_directory": str(model_dir)}), flush=True
    )


if __name__ == "__main__":
    main()
