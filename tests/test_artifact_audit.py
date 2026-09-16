import json
from decimal import Decimal

import pytest

from copromem.artifact_audit import audit_store
from copromem.checkpoints import GenerationService, IntegrityError, RunStore
from copromem.paired_gsm8k import GSM8KAdapter, PairedConfig
from copromem.real_gsm8k_experiment import CallResult, Example, Usage


def test_saved_generation_and_checkpoint_pass_but_tampering_fails(tmp_path):
    class Client:
        model = "mock"

        def chat(self, system, user, max_tokens, *, seed=None):
            return CallResult("{}", Usage(), self.model)

    adapter = GSM8KAdapter(
        GenerationService(Client(), RunStore(tmp_path), "audit"), PairedConfig()
    )
    adapter.checkpoint(Example("a", "public question", Decimal(1)), "build", 0)
    assert audit_store(tmp_path)["completed_generations"] == 1
    path = next((tmp_path / "calls").glob("*.json"))
    value = json.loads(path.read_text())
    value["response"]["text"] = "tampered"
    path.write_text(json.dumps(value))
    with pytest.raises(IntegrityError):
        audit_store(tmp_path)
