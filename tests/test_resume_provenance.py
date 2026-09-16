import pytest

from copromem.checkpoints import IntegrityError, RunStore, digest


@pytest.mark.parametrize("persisted", [False, True])
def test_resume_requires_identical_code_and_environment(tmp_path, persisted):
    store = RunStore(tmp_path if persisted else None)
    original = {"source_hashes": {"miner.py": "original"}, "python": "3.13.5"}
    # Simulate the digest-named records written by the earlier CLI.
    store.write("provenance", digest(original), original)
    if persisted:
        store = RunStore(tmp_path)
    store.bind_provenance(original)
    changed = {**original, "source_hashes": {"miner.py": "changed"}}
    with pytest.raises(IntegrityError, match="new preregistered cycle"):
        store.bind_provenance(changed)
    assert store.read("provenance", digest(original)) == original
    assert store.read("provenance", digest(changed)) is None


def test_new_run_binds_first_provenance(tmp_path):
    store = RunStore(tmp_path)
    original = {"source_hashes": {"miner.py": "first"}, "python": "3.13.5"}
    store.bind_provenance(original)
    assert store.read("provenance", digest(original)) == original
