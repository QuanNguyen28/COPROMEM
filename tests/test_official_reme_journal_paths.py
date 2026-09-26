from pathlib import Path

from research.official_pilot.upstream_executor import safe_journal_path


def test_wsl_e_drive_journal_path_is_created_and_provenance_safe(tmp_path: Path) -> None:
    # Mirrors the E-backed WSL layout and the original colon-bearing ID.
    parent = tmp_path / "mnt" / "e" / "Project" / "AAMAS" / "journals"
    trajectory_id = "acquisition:07b42fd_1:seed=7101"
    path = safe_journal_path(parent, trajectory_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    assert path.parent.exists()
    assert ":" not in path.name
    assert path.name == "acquisition_07b42fd_1_seed_7101.jsonl"
    # The original identifier is intentionally retained in each record,
    # rather than inferred from a sanitized filename.
    path.write_text('{"trajectory_id":"' + trajectory_id + '"}\n', encoding="utf-8")
    assert trajectory_id in path.read_text(encoding="utf-8")
