import hashlib
import runpy
from pathlib import Path

import pytest

from copromem.checkpoints import IntegrityError

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "research/scripts/audit_public_presence.py")
)


def test_saved_api_prefix_must_bind_to_complete_native_bytes():
    raw = b'{"call":1}\n{"call":2}\n'
    first = b'{"call":1}\n'
    prefix = {
        "bytes": len(first),
        "sha256": hashlib.sha256(first).hexdigest(),
        "entries": 1,
    }
    MODULE["verify_log_prefix"](raw, prefix)
    for changed in [
        {**prefix, "entries": 2},
        {**prefix, "sha256": "changed"},
        {**prefix, "bytes": len(raw) + 1},
        {**prefix, "bytes": len(first) - 1},
        {**prefix, "values": "not allowed"},
    ]:
        with pytest.raises(IntegrityError):
            MODULE["verify_log_prefix"](raw, changed)
