from __future__ import annotations

from scripts.audit_v54_effect_path_012 import _program_call_evidence


def test_program_level_response_attestation_is_not_direct_effect_observation():
    history = [
        {"role": "assistant", "content": "for artist_id in artist_ids:\n    apis.spotify.follow_artist(artist_id)"},
        {"role": "user", "content": "native program completed"},
    ]
    row = _program_call_evidence(history)[0]
    assert row["operation"] == "apis.spotify.follow_artist"
    assert row["program_response_observed"] is True
    assert row["direct_statement"] is False
    assert row["control_context"] == ["For"]


def test_direct_effect_call_is_distinguished_from_nested_call():
    history = [
        {"role": "assistant", "content": "apis.spotify.follow_artist(artist_id)"},
        {"role": "user", "content": "native program completed"},
    ]
    row = _program_call_evidence(history)[0]
    assert row["program_response_observed"] is True
    assert row["direct_statement"] is True
    assert row["control_context"] == []
