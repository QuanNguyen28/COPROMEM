import hashlib
import json
import zlib
from dataclasses import asdict

import pytest

from copromem.checkpoints import IntegrityError, RunStore, canonical, digest
from copromem.official_source import (
    HORIZONTAL_RULE,
    audit_extracted_source,
    parse_public_log,
    selected_member_names,
)


def fixture(tmp_path):
    store = RunStore(tmp_path)
    task = "123abcd_1"
    run = "agent/model/train"
    text = f"\n### Environment Interaction 1\n{HORIZONTAL_RULE}\n```python\nprint('toy')\n```\n\n```\ntoy\n```\n\n\n"
    payloads = {
        "logs/environment_io.md": text.encode(),
        "logs/api_calls.jsonl": b"{}\n",
        "version/code.txt": b"0.1.0",
        "version/data.txt": b"0.1.0",
    }
    names = selected_member_names(run, [task])
    request = {
        "run": run,
        "tasks": [task],
        "members": {
            name: {
                "bytes": len(payloads[name.split(task + "/")[1]]),
                "crc": zlib.crc32(payloads[name.split(task + "/")[1]]),
            }
            for name in names
        },
    }
    protocol = {"request": request}
    key = digest(protocol)
    selected = tmp_path / "selected_public" / key
    files = {}
    for name, data in payloads.items():
        path = selected / "raw" / task / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        files[f"{task}/{name}"] = {
            "archive_member": f"{run}/tasks/{task}/{name}",
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    parsed = {
        "task_id": task,
        "versions": {"code": "0.1.0", "data": "0.1.0"},
        "interactions": [asdict(row) for row in parse_public_log(text)],
        "source_log_sha256": hashlib.sha256(text.encode()).hexdigest(),
    }
    (selected / "parsed").mkdir()
    (selected / "parsed" / (task + ".json")).write_text(
        canonical(parsed), encoding="utf-8"
    )
    report = {
        "members_read": names,
        "request_digest": digest(request),
        "files": files,
        "tasks": [
            {
                "task_id": task,
                "parse_status": "parsed",
                "parsed_digest": digest(parsed),
                "interactions": 1,
                "versions": parsed["versions"],
            }
        ],
    }
    (selected / "extraction_report.json").write_text(
        canonical(report), encoding="utf-8"
    )
    store.write("public_extraction_protocols", key, protocol)
    store.write(
        "public_extraction_reports",
        key,
        {"protocol_digest": key, "selected_directory": str(selected), "report": report},
    )
    return store, key, selected


def test_source_audit_regenerates_every_field(tmp_path):
    store, key, _ = fixture(tmp_path)
    audit = audit_extracted_source(store, key)
    assert audit["raw_files_verified"] == 4 and audit["tasks"] == ["123abcd_1"]


def test_source_audit_rejects_modified_raw_bytes(tmp_path):
    store, key, selected = fixture(tmp_path)
    (selected / "raw/123abcd_1/version/data.txt").write_bytes(b"0.2.0")
    with pytest.raises(IntegrityError, match="bytes/hash/ZIP CRC"):
        audit_extracted_source(store, key)


def test_source_audit_rejects_parsed_code_substitution(tmp_path):
    store, key, selected = fixture(tmp_path)
    path = selected / "parsed/123abcd_1.json"
    data = json.loads(path.read_text())
    data["interactions"][0]["code"] = "print('replacement')"
    path.write_text(canonical(data), encoding="utf-8")
    with pytest.raises(IntegrityError, match="regenerate losslessly"):
        audit_extracted_source(store, key)


def test_source_audit_rejects_extra_file_or_changed_report(tmp_path):
    store, key, selected = fixture(tmp_path)
    (selected / "raw/unselected.txt").write_text("extra", encoding="utf-8")
    with pytest.raises(IntegrityError, match="extra, missing"):
        audit_extracted_source(store, key)


def test_source_audit_rejects_unbound_report(tmp_path):
    store, key, selected = fixture(tmp_path)
    (selected / "extraction_report.json").write_text("{}", encoding="utf-8")
    with pytest.raises(IntegrityError, match="report no longer matches"):
        audit_extracted_source(store, key)
