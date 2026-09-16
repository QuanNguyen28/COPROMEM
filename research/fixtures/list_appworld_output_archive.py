"""ZIP central-directory metadata only; never read or extract member bodies."""

import hashlib
import io
import json
import os
import zipfile
from collections import Counter
from pathlib import Path

from appworld.common.constants import PASSWORD, SALT
from appworld.common.utils import decrypt_bytes

BUILD = {
    "27e1026_1",
    "b7a9ee9_1",
    "60d0b5b_1",
    "aa8502b_1",
    "ce359b5_1",
    "cf6abd2_1",
    "287e338_1",
    "3c13f5a_1",
}


def main():
    filename = os.environ.get("ARCHIVE_FILENAME", "experiment-outputs-0.1.0.bundle")
    if filename not in {
        "experiment-outputs-0.1.0.bundle",
        "experiment-outputs-0.1.3.bundle",
    }:
        raise ValueError("unregistered output archive")
    raw = (Path("/archive") / filename).read_bytes()
    data = decrypt_bytes(raw, PASSWORD, SALT)
    counts, byte_counts, prefixes, selected = Counter(), Counter(), Counter(), []
    with zipfile.ZipFile(io.BytesIO(data), "r") as archive:
        # infolist reads central-directory metadata, not member payloads.
        for member in archive.infolist():
            parts = member.filename.split("/")
            if (
                member.filename.startswith("/")
                or ".." in parts
                or "\\" in member.filename
            ):
                raise ValueError("unsafe archive member name")
            experiment = parts[0]
            counts[experiment] += 1
            byte_counts[experiment] += member.file_size
            prefixes["/".join(parts[:3])] += 1
            train_labelled = any(
                part == "train" or part.endswith("_train") for part in parts[:-1]
            )
            if train_labelled and BUILD.intersection(parts):
                selected.append(
                    {
                        "path": member.filename,
                        "bytes": member.file_size,
                        "compressed_bytes": member.compress_size,
                        "crc": member.CRC,
                    }
                )
    print(
        json.dumps(
            {
                "kind": "central-directory metadata only; zero ZIP member payloads opened",
                "archive_sha256": hashlib.sha256(raw).hexdigest(),
                "decrypted_zip_sha256": hashlib.sha256(data).hexdigest(),
                "experiment_member_counts": dict(sorted(counts.items())),
                "experiment_uncompressed_bytes": dict(sorted(byte_counts.items())),
                "three_level_member_prefix_counts": dict(sorted(prefixes.items())),
                "selected_build_train_member_metadata": selected,
                "total_members": sum(counts.values()),
                "paid_calls": 0,
                "task_executions": 0,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
