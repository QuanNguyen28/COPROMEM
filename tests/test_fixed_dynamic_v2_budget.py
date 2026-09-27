from research.scripts.freeze_corrected_fixed_dynamic_v2_manifest import NEW_ACQUISITION, budget


def test_v2_uses_eight_new_acquisition_ids_from_eight_new_families():
    assert len(NEW_ACQUISITION) == 8
    assert len({task.split("_", 1)[0] for task in NEW_ACQUISITION}) == 8


def test_v2_minimum_evaluation_envelope_is_fail_closed_at_140_usd():
    value = budget(16)
    assert value["all_in_usd"] > value["hard_cap_usd"]
    assert not value["fits_hard_cap"]
