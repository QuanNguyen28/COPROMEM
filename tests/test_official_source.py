import io
import stat
import zipfile

import pytest

from copromem.checkpoints import IntegrityError
from copromem.official_source import (
    HORIZONTAL_RULE,
    parse_public_log,
    selected_member_names,
    validate_member_inventory,
)


def log(code="print('toy')", output="toy", index=1, label="Environment Interaction"):
    return f"\n### {label} {index}\n{HORIZONTAL_RULE}\n```python\n{code}\n```\n\n```\n{output}\n```\n\n\n"


def test_parser_preserves_exact_code_and_output_spans():
    code = "text = '''a  \nb  '''\nprint(text)  "
    text = log(code, "a  \nb  ") + log("print(2)", "2", 2, "Execution")
    rows = parse_public_log(text)
    assert len(rows) == 2 and rows[0].code == code
    assert rows[0].output == "a  \nb  "
    for row in rows:
        assert text[row.code_start : row.code_end] == row.code
        assert text[row.output_start : row.output_end] == row.output


@pytest.mark.parametrize(
    "text",
    [
        "",
        "prefix" + log(),
        log(index=2),
        log() + "trailing",
        log().replace("\n", "\r\n"),
        log().replace("\n```\n\n```\n", "\n```\n```\n"),
        log("x = '''\n```\n'''"),
        log(output="text\n```\ntrailing"),
    ],
)
def test_parser_rejects_ambiguous_or_unbound_log(text):
    with pytest.raises(IntegrityError):
        parse_public_log(text)


def test_selected_files_exclude_db_evaluator_and_other_tasks():
    names = selected_member_names("agent/model/train", ["123abcd_1"])
    assert len(names) == 4 and all("/tasks/123abcd_1/" in name for name in names)
    assert not any("/dbs/" in name or "/evaluation/" in name for name in names)


@pytest.mark.parametrize(
    "run,tasks",
    [
        ("agent/model/test_normal", ["123abcd_1"]),
        ("../train", ["123abcd_1"]),
        ("agent/train", ["../bad"]),
        ("agent/train", ["123abcd_1", "123abcd_1"]),
        ("agent/train", []),
    ],
)
def test_selection_rejects_unsafe_or_unregistered_identity(run, tasks):
    with pytest.raises(IntegrityError):
        selected_member_names(run, tasks)


def metadata():
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as archive:
        archive.writestr(
            "agent/model/train/tasks/123abcd_1/logs/environment_io.md", "toy"
        )
    with zipfile.ZipFile(raw) as archive:
        infos = archive.infolist()
    info = infos[0]
    return infos, {
        info.filename: {
            "bytes": info.file_size,
            "compressed_bytes": info.compress_size,
            "crc": info.CRC,
        }
    }


def test_inventory_checks_exact_metadata_before_reading_payloads():
    infos, expected = metadata()
    validate_member_inventory(infos, expected)
    with pytest.raises(IntegrityError, match="duplicate"):
        validate_member_inventory(infos * 2, expected)
    with pytest.raises(IntegrityError, match="missing"):
        validate_member_inventory([], expected)
    with pytest.raises(IntegrityError, match="metadata"):
        validate_member_inventory(
            infos, {infos[0].filename: {**expected[infos[0].filename], "crc": 0}}
        )
    with pytest.raises(IntegrityError, match="size cap"):
        validate_member_inventory(infos, expected, per_file_cap=2)
    with pytest.raises(IntegrityError, match="total"):
        validate_member_inventory(infos, expected, total_cap=2)
    infos[0].external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(IntegrityError, match="symlink"):
        validate_member_inventory(infos, expected)
