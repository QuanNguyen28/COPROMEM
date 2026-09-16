import runpy
from pathlib import Path

MODULE = runpy.run_path(
    str(Path(__file__).parents[1] / "research/scripts/preflight_public_observation.py")
)


def test_full_envelope_capabilities_are_blocked_but_public_references_are_allowed():
    report = MODULE["check_capabilities"]()
    assert not report["required_capabilities_accepted"]
    assert [row["accepted_by_frozen_policy"] for row in report["rows"]] == [
        False,
        False,
        True,
    ]
    assert report["rows"][0]["forbidden_identifiers"] == ["globals"]
    assert report["rows"][1]["forbidden_identifiers"] == ["type"]
