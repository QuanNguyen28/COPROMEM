"""Fetch pinned official text assets and extract one outcome-blind train fixture."""

from __future__ import annotations

import hashlib
import json
import stat
import urllib.request
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from copromem.checkpoints import IntegrityError, RunStore, digest

REVISION = "9da74e4a7af532d4aea9b042628bc759a1fab0de"
ASSETS = (
    (112282473, "json_2.1.1_json.zip", 72_018_818),
    (112282926, "json_2.1.1_pddl.zip", 34_881_784),
    (154128788, "json_2.1.1_tw-pddl.zip", 45_059_629),
)


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download_new(
    url: str, destination: Path, *, max_bytes: int, expected_size: int | None = None
) -> None:
    if destination.exists():
        raise FileExistsError("download never overwrites an existing destination")
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part-" + uuid.uuid4().hex)
    with (
        urllib.request.urlopen(url, timeout=45) as response,
        partial.open("xb") as output,
    ):
        written = 0
        while chunk := response.read(1024 * 1024):
            written += len(chunk)
            if written > max_bytes:
                raise ValueError("public asset exceeds its download bound")
            output.write(chunk)
    if expected_size is not None and written != expected_size:
        raise IntegrityError("release asset size differs from pinned metadata")
    partial.rename(destination)


def safe_member(info: zipfile.ZipInfo) -> PurePosixPath:
    path = PurePosixPath(info.filename)
    if (
        "\\" in info.filename
        or "\\" in info.orig_filename
        or path.is_absolute()
        or any(part in {"..", "."} or ":" in part for part in path.parts)
    ):
        raise ValueError("unsafe archive path")
    if stat.S_ISLNK(info.external_attr >> 16):
        raise ValueError("archive symlinks are not extracted")
    if info.file_size > 20_000_000:
        raise ValueError("selected text member exceeds size cap")
    return path


def select_task(json_paths: set[str], game_paths: set[str]) -> tuple[str, int]:
    candidates = {
        str(PurePosixPath(path).parent)
        for path in json_paths
        if path.startswith("json_2.1.1/train/") and path.endswith("/traj_data.json")
    } & {
        str(PurePosixPath(path).parent)
        for path in game_paths
        if path.endswith("/game.tw-pddl")
    }
    candidates = {
        path for path in candidates if "movable" not in path and "Sliced" not in path
    }
    if not candidates:
        raise ValueError("no common supported train-path candidates")
    return min(candidates, key=lambda path: digest([160906, path])), len(candidates)


def main():
    root = Path(__file__).resolve().parents[2]
    store = RunStore(root / "artifacts/research/alfworld_native_probe_20260916")
    archives = []
    for asset_id, name, size in ASSETS:
        record = store.read("release_assets", str(asset_id))
        destination = store.root / "archives" / name
        if record is None:
            url = f"https://api.github.com/repos/alfworld/alfworld/releases/assets/{asset_id}"
            with urllib.request.urlopen(url, timeout=45) as response:
                metadata = json.load(response)
            if (metadata["id"], metadata["name"], metadata["size"]) != (
                asset_id,
                name,
                size,
            ):
                raise IntegrityError("release asset identity changed")
            store.write("remote_asset_metadata", str(asset_id), metadata)
            download_new(
                metadata["browser_download_url"],
                destination,
                max_bytes=size,
                expected_size=size,
            )
            record = {
                "metadata": metadata,
                "sha256": sha256(destination),
                "path": str(destination),
                "checksum_note": "Recorded local hash; legacy GitHub asset has no published digest.",
            }
            store.write("release_assets", str(asset_id), record)
        if (
            destination.stat().st_size != size
            or sha256(destination) != record["sha256"]
        ):
            raise IntegrityError("cached official release asset is corrupted")
        archives.append(destination)
        print(
            json.dumps({"asset": name, "bytes": size, "sha256": record["sha256"]}),
            flush=True,
        )
    with (
        zipfile.ZipFile(archives[0]) as json_archive,
        zipfile.ZipFile(archives[2]) as game_archive,
    ):
        chosen, count = select_task(
            set(json_archive.namelist()), set(game_archive.namelist())
        )
    selection = {
        "seed": 160906,
        "candidate_train_paths": count,
        "selected_directory": chosen,
        "selection_uses_contents_or_outcomes": False,
        "official_validation_or_test_extracted": False,
    }
    store.write("selection", "train_fixture", selection)
    destination_root = (store.root / "selected_data").resolve()
    extracted = {}
    for archive in archives:
        with zipfile.ZipFile(archive) as stream:
            for info in stream.infolist():
                if info.is_dir() or str(PurePosixPath(info.filename).parent) != chosen:
                    continue
                member = safe_member(info)
                if member.suffix not in {".json", ".pddl", ".tw-pddl"}:
                    raise ValueError(
                        "selected fixture contains an unexpected non-text file"
                    )
                destination = (destination_root / Path(*member.parts)).resolve()
                if not destination.is_relative_to(destination_root):
                    raise ValueError(
                        "selected extraction target escaped its data directory"
                    )
                payload = stream.read(info)
                expected_hash = hashlib.sha256(payload).hexdigest()
                if destination.exists():
                    if sha256(destination) != expected_hash:
                        raise IntegrityError("existing extracted file differs")
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with destination.open("xb") as output:
                        output.write(payload)
                extracted[info.filename] = {
                    "archive": archive.name,
                    "bytes": len(payload),
                    "sha256": expected_hash,
                }
    logic_files = {}
    for name in ("alfred.pddl", "alfred.twl2"):
        url = f"https://raw.githubusercontent.com/alfworld/alfworld/{REVISION}/alfworld/data/{name}"
        destination = destination_root / "logic" / name
        archived = store.read("logic_files", name)
        if archived is None:
            download_new(url, destination, max_bytes=4_000_000)
            archived = {
                "source_url": url,
                "sha256": sha256(destination),
                "bytes": destination.stat().st_size,
            }
            store.write("logic_files", name, archived)
        if sha256(destination) != archived["sha256"]:
            raise IntegrityError("pinned engine logic file is corrupted")
        logic_files[name] = archived
    manifest = {
        "selection": selection,
        "data_directory": str(destination_root),
        "files": extracted,
        "logic": logic_files,
        "alfworld_revision": REVISION,
        "release_asset_ids": [row[0] for row in ASSETS],
        "model_calls": 0,
        "interpretation": "One hash-selected train-only native fixture. Current default generated games are not assumed identical to historical ExpeL paper data; no policy or success claim.",
    }
    key = digest(manifest)
    store.write("data_manifests", key, manifest)
    print(
        json.dumps(
            {
                "manifest_id": key,
                "selection": selection,
                "extracted_text_files": len(extracted),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
