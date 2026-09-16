"""Constructed information-loss counterexamples, not native task results."""

import runpy
from pathlib import Path

INPUT = runpy.run_path(
    str(Path(__file__).parents[1] / "research/scripts/monitor_proposal_inputs.py")
)


def public(program):
    return {
        "program": program,
        "envelope": {
            "version": INPUT["CHECK"]["PUBLIC"]["VERSION"],
            "bindings": [
                {"name": "selected", "present": False},
                {"name": "song_details", "present": True},
            ],
        },
    }


def test_frozen_redaction_erases_a_semantically_decisive_genre_filter():
    intended = public("selected = song_details['genre'] == 'classical'")
    changed = public(
        "selected = song_details['genre'] == '__counterexample_other_genre__'"
    )
    assert INPUT["runtime_input"](intended) == INPUT["runtime_input"](changed)
    # Direct predicate truth on a constructed public-schema-compatible item.
    # Neither target program nor a native benchmark episode is executed.
    item = {"genre": "classical"}
    assert item["genre"] == "classical"
    assert item["genre"] != "__counterexample_other_genre__"


def test_first_artist_selection_is_not_a_universal_all_artist_certificate():
    view = INPUT["runtime_input"](public("selected = song_details['artists'][0]['id']"))
    outcomes = []
    for artists in ([{"id": 1}], [{"id": 1}, {"id": 2}]):
        # Hypothetical worlds: one qualifying song, neither artist followed yet.
        # Both use the same code/name-presence view; response values are omitted.
        selected = {artists[0]["id"]}
        required = {artist["id"] for artist in artists}
        outcomes.append(selected == required)
        assert view == INPUT["runtime_input"](
            public("selected = song_details['artists'][0]['id']")
        )
    assert outcomes == [True, False]
