"""Constructed control fixtures; no benchmark target program is executed."""

import copy
import runpy
from pathlib import Path

import pytest

M = runpy.run_path(
    str(Path(__file__).parents[1] / "research/scripts/manual_coverage_control.py")
)
TASK = "Follow all the artists who have sung at least one song I have liked on Spotify."
CLASSICAL = (
    "Follow all artists of all classical-genre songs in any of my playlists on Spotify."
)


def docs():
    result = {}
    for api in ("show_liked_songs", "show_playlist_library", "follow_artist"):
        result["spotify." + api] = {
            "app_name": "spotify",
            "api_name": api,
            "path": "/fixture",
            "method": "GET",
            "description": "Public fixture",
            "response_schemas": {"success": []},
            "parameters": [
                {"name": "page_index", "default": 0},
                {"name": "page_limit", "default": 5},
            ],
        }
    return result


def view(program, task=TASK, present=True):
    names = M["VIEW"]["CHECK"]["PUBLIC"]["selected_names"]([program])
    raw = {
        "program": program,
        "envelope": {
            "version": M["VIEW"]["CHECK"]["PUBLIC"]["VERSION"],
            "bindings": [{"name": n, "present": present} for n in names],
        },
    }
    return M["VIEW"]["build_view"](raw, task, docs())[0]


PROGRAM = """page = 0
items = []
while True:
    response = apis.spotify.show_liked_songs(page_index=page)
    if not response:
        break
    items.extend(response)
    page += 1
for song in items:
    print(song)
"""


def check(program, task=TASK, present=True):
    return M["inspect"](view(program, task, present))


def test_single_page_and_empty_producer_warn():
    assert (
        check(
            "items = apis.spotify.show_liked_songs()\nfor item in items:\n    print(item)"
        )["pagination"]["status"]
        == "risk"
    )
    assert (
        check("items=[]\nfor item in items:\n    print(item)")["pagination"]["status"]
        == "risk"
    )


def test_recognized_pattern_is_not_a_universal_certificate_and_alpha_renames():
    a = check(PROGRAM)
    b = check(
        PROGRAM.replace("page", "counter")
        .replace("counter_index", "page_index")
        .replace("items", "collection")
        .replace("response", "batch")
    )
    assert a == b
    assert a["decision"] == "no_detected_risk"
    assert (
        "API_stability_termination_and_downstream_correctness_not_proved"
        in a["pagination"]["reasons"]
    )


def test_no_advance_warns_but_unrecognized_valid_advance_abstains():
    assert check(PROGRAM.replace("    page += 1\n", ""))["decision"] == "warn"
    assert (
        check(PROGRAM.replace("page += 1", "page = page + 1"))["decision"] == "abstain"
    )


def test_wrong_collection_and_extra_exit_do_not_pass_from_loop_presence():
    assert (
        check(PROGRAM.replace("items.extend(response)", "other.extend(response)"))[
            "decision"
        ]
        == "abstain"
    )
    assert (
        check(PROGRAM.replace("    page += 1", "    break\n    page += 1"))["decision"]
        == "abstain"
    )


def test_page_start_and_collector_entry_presence_are_checked():
    assert check(PROGRAM.replace("page = 0", "page = 1"))["decision"] == "abstain"
    assert (
        check(PROGRAM.replace("items = []\n", ""), present=False)["decision"]
        == "abstain"
    )
    result = check(PROGRAM.replace("items = []\n", ""), present=True)
    assert result["decision"] == "no_detected_risk"
    assert (
        "preexisting_collector_value_and_type_are_unobserved"
        in result["pagination"]["reasons"]
    )


def test_conditional_body_idiom_and_short_page_assumption():
    conditional = "page=0\nitems=[]\nwhile True:\n    response=apis.spotify.show_liked_songs(page_index=page)\n    if response:\n        items.extend(response)\n        page += 1\n    else:\n        break\nfor item in items:\n    print(item)"
    assert check(conditional)["pagination"]["status"] == "pattern_observed"
    short = PROGRAM.replace(
        "    page += 1", "    if len(response) < 5:\n        break\n    page += 1"
    )
    assert (
        "short_page_termination_requires_an_API_guarantee_not_established_here"
        in check(short)["pagination"]["reasons"]
    )


def test_changed_genre_and_first_artist_have_separate_risk_reasons():
    program = "selected = song['genre'] == 'jazz'\nartist_id=song['artists'][0]['id']\napis.spotify.follow_artist(artist_id=artist_id)"
    r = check(program, CLASSICAL)
    assert len(r["consumer_risks"]) == 2
    r2 = check(program.replace("'jazz'", "'classical'"), CLASSICAL)
    assert len(r2["consumer_risks"]) == 1
    r3 = check(
        program.replace("artist_id=artist_id", "artist_id=another_id").replace(
            "'jazz'", "'classical'"
        ),
        CLASSICAL,
    )
    assert r3["consumer_risks"] == []


def test_task_scope_not_dataset_ids_and_target_program_not_executed():
    assert check(PROGRAM, "Follow one artist on Spotify")["decision"] == "abstain"
    assert (
        check(PROGRAM + "\nraise RuntimeError('not executed')")["pagination"]["status"]
        == "pattern_observed"
    )


def test_public_inputs_immutable_and_label_fields_rejected():
    v = view("access_token='fixture-private-auth'\n" + PROGRAM)
    saved = copy.deepcopy(v)
    M["inspect"](v)
    assert v == saved
    assert "fixture-private-auth" not in str(v)
    with pytest.raises(ValueError):
        M["inspect"]({**v, "native_success": True})
    v["api_docs"]["spotify.follow_artist"]["native_success"] = True
    with pytest.raises(ValueError):
        M["inspect"](v)
