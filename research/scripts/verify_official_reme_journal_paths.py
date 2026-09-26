#!/usr/bin/env python3
"""Zero-cost regression check for colon-bearing E-drive/WSL journal IDs."""
from __future__ import annotations

import pathlib
import tempfile

from research.official_pilot.upstream_executor import safe_journal_path


def main() -> None:
    with tempfile.TemporaryDirectory(dir="/mnt/e/Project/AAMAS") as root:
        parent = pathlib.Path(root) / "nested" / "journals"
        original = "acquisition:07b42fd_1:seed=7101"
        journal = safe_journal_path(parent, original)
        journal.parent.mkdir(parents=True, exist_ok=True)
        assert journal.name == "acquisition_07b42fd_1_seed_7101.jsonl"
        assert ":" not in journal.name
        journal.write_text('{"trajectory_id":"' + original + '"}\n', encoding="utf-8")
        assert original in journal.read_text(encoding="utf-8")
    print("official_reme_journal_path_regression=passed")


if __name__ == "__main__":
    main()
