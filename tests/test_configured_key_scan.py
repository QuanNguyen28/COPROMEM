import runpy
from pathlib import Path


def test_exact_byte_scan_detects_chunk_boundary_match(tmp_path):
    module = runpy.run_path(
        str(Path(__file__).parents[1] / "research/scripts/scan_configured_key.py")
    )
    needle = b"constructed-fixture-not-a-credential"
    data = b"x" * (1024 * 1024 - 5) + needle + b"suffix"
    path = tmp_path / "fixture.bin"
    path.write_bytes(data)
    assert module["contains_bytes"](path, needle) == (True, len(data))
    assert module["contains_bytes"](path, b"absent-fixture") == (False, len(data))
