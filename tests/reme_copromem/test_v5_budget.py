from __future__ import annotations

import pytest

from copromem.experiments.reme_copromem.runner import v5_budget_bound


def test_v5_registered_budget_covers_every_provider_role_and_contingency():
    bound = v5_budget_bound(call_limits={"executor": 720, "reme_lifecycle": 50,
                                         "reme_embedding": 50, "copromem_decomposition": 0})
    assert bound["executor_usd"] == pytest.approx(8.84736)
    assert bound["reme_lifecycle_usd"] == pytest.approx(2.08896)
    assert bound["embedding_usd"] == pytest.approx(0.08192)
    assert bound["dispatchable_usd"] == pytest.approx(11.01824)
    assert bound["non_dispatchable_contingency_usd"] == pytest.approx(1.652736)
    assert bound["all_in_usd"] == pytest.approx(12.670976)
