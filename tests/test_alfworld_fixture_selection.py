import importlib.util
import stat
import zipfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "alfworld_fetch",
    Path(__file__).parents[1] / "research/scripts/fetch_alfworld_fixture.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_selection_is_order_invariant_train_only_and_ignores_native_unsupported_paths():
    dirs = [
        "json_2.1.1/train/a/trial",
        "json_2.1.1/train/b/trial",
        "json_2.1.1/valid_unseen/c/trial",
        "json_2.1.1/train/movable/trial",
        "json_2.1.1/train/Sliced/trial",
    ]
    jsons = {path + "/traj_data.json" for path in dirs}
    games = {path + "/game.tw-pddl" for path in dirs}
    selected, count = module.select_task(jsons, games)
    assert count == 2 and selected in dirs[:2]
    reversed_jsons = sorted(jsons, reverse=True)
    assert module.select_task(set(reversed_jsons), games) == (selected, count)


@pytest.mark.parametrize(
    "name",
    ["../../outside.json", "/absolute.json", "C:/outside.json", "a\\outside.json"],
)
def test_unsafe_zip_paths_are_rejected(name):
    with pytest.raises(ValueError):
        module.safe_member(zipfile.ZipInfo(name))


def test_archive_symlink_is_rejected():
    info = zipfile.ZipInfo("path/link.json")
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(ValueError, match="symlinks"):
        module.safe_member(info)
