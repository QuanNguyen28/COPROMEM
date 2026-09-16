import hashlib

import pytest

from copromem.checkpoints import IntegrityError, RunStore, digest
from copromem.stateful_source import select_groups


def fixture(tmp_path):
    native = tmp_path / "native"
    (native / "datasets").mkdir(parents=True)
    manifest = native / "datasets/train.txt"
    manifest.write_text(
        "\n".join(
            f"{group:07x}_{variant}" for group in range(25) for variant in (3, 1, 2)
        )
    )
    prior = {
        "selection_seed": 160906,
        "excluded_scenarios": ["07b42fd"],
        "build_groups": 4,
        "dev_groups": 4,
        "audit_groups": 3,
        "evaluation_groups": 4,
    }
    selected = select_groups(native, prior)
    registry = RunStore(tmp_path / "registry")
    registry.write("protocol", "preregistration", prior)
    registry.write("dataset", "selection", selected)
    extension = {
        **prior,
        "source_extension": {
            "version": "unallocated-build-v1",
            "registry_store": str(registry.root),
            "protocol_digest": digest(prior),
            "selection_digest": digest(selected),
            "train_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        },
    }
    return native, prior, selected, extension


def test_extension_preserves_every_previous_group_and_uses_only_identifiers(
    tmp_path, monkeypatch
):
    native, prior, old, config = fixture(tmp_path)
    from pathlib import Path

    original = Path.read_text

    def guarded(path, *args, **kwargs):
        assert path.name in {"train.txt", "preregistration.json", "selection.json"}
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded)
    new = select_groups(native, config)
    assert new == select_groups(native, config)
    assert select_groups(native, prior) == old
    assert new["previous_build"] == old["build"]
    for split in ("dev", "audit", "evaluation"):
        assert new[split] == old[split]
    allocated = {task.split("_")[0] for rows in old.values() for task in rows}
    expected = sorted(
        {f"{i:07x}" for i in range(25)} - allocated,
        key=lambda group: digest([160906, group]),
    )[:4]
    assert new["build"] == [group + "_1" for group in expected]
    assert not allocated & {task.split("_")[0] for task in new["build"]}


@pytest.mark.parametrize(
    "field", ["protocol_digest", "selection_digest", "train_manifest_sha256"]
)
def test_extension_rejects_corrupt_registry_or_manifest(tmp_path, field):
    native, _, _, config = fixture(tmp_path)
    config["source_extension"][field] = "0" * 64
    with pytest.raises(IntegrityError):
        select_groups(native, config)


@pytest.mark.parametrize(
    "change",
    [
        {"selection_seed": 8},
        {"excluded_scenarios": ["07b42fd", "0000001"]},
        {"dev_groups": 0},
        {"audit_groups": 0},
        {"evaluation_groups": 0},
    ],
)
def test_extension_cannot_reassign_reserved_groups(tmp_path, change):
    native, _, _, config = fixture(tmp_path)
    with pytest.raises(IntegrityError):
        select_groups(native, {**config, **change})


def test_extension_rejects_insufficient_remaining_groups(tmp_path):
    native, _, _, config = fixture(tmp_path)
    with pytest.raises(ValueError, match="unallocated"):
        select_groups(native, {**config, "build_groups": 11})


def test_extension_rejects_unknown_version(tmp_path):
    native, _, _, config = fixture(tmp_path)
    config["source_extension"]["version"] = "unregistered"
    with pytest.raises(ValueError, match="version"):
        select_groups(native, config)


def test_correct_digest_does_not_legitimize_a_changed_prior_partition(tmp_path):
    native, prior, old, config = fixture(tmp_path)
    forged = {**old, "build": old["dev"], "dev": old["build"]}
    registry = RunStore(tmp_path / "forged")
    registry.write("protocol", "preregistration", prior)
    registry.write("dataset", "selection", forged)
    config["source_extension"].update(
        registry_store=str(registry.root), selection_digest=digest(forged)
    )
    with pytest.raises(IntegrityError, match="reproduce"):
        select_groups(native, config)
