from __future__ import annotations

import json
import pytest

from copromem.experiments.reme_copromem import task_conditioned_retrieval_v625 as v
from copromem.experiments.reme_copromem.public_operation_intent_registry import digest
from copromem.experiments.reme_copromem.schema_external_admission import receipt


def registry():
    return {
        "registry_sha256": "r",
        "normalization": {"operation_aliases": {}},
        "operations": [
            {"operation": "apis.venmo.create_transaction", "http_method": "POST", "access_mode": "write"},
            {"operation": "apis.venmo.create_payment_request", "http_method": "POST", "access_mode": "write"},
            {"operation": "apis.phone.search_contacts", "http_method": "GET", "access_mode": "read"},
        ],
    }


def intents():
    value = {
        "version": "appworld-public-operation-intent-registry-v1",
        "sources": [],
        "operations": [
            {"operation": "apis.venmo.create_payment_request", "app": "venmo", "http_method": "POST",
             "description": "Send a payment request.",
             "description_tokens": ["payment", "request", "send"]},
            {"operation": "apis.venmo.create_transaction", "app": "venmo", "http_method": "POST",
             "description": "Send money to a user.",
             "description_tokens": ["money", "send", "to", "user"]},
        ],
    }
    value["intent_registry_sha256"] = digest(value)
    return value


def meta():
    return {"app_descriptions": {"venmo": "public"}, "public_operation_intents": intents()}


def schema(identifier: str, *, terminal: str = "apis.venmo.create_transaction", prior: bool = True):
    required = ["apis.phone.search_contacts", terminal] if prior else [terminal]
    typed = []
    if prior:
        typed.append({"operation": "apis.phone.search_contacts", "occurrence_index": 1,
                      "required": ["query"], "outputs": ["receiver_email"]})
    typed.append({"operation": terminal, "occurrence_index": len(required),
                  "required": ["amount", "receiver_email"], "outputs": ["message"]})
    return {
        "policy_version": "copromem-v6.1-semantic-graph-v1",
        "registry_sha256": "r",
        "required_operations": required,
        "terminal_effect": terminal,
        "terminal_occurrence_id": f"{terminal}#1",
        "typed_constraints": typed,
        "support": {"successes": 2},
    }


def state(*rows: tuple[str, dict]):
    return {"contrastive_v6_schemas": dict(rows)}


def admission(value, ids):
    return receipt(bank_sha256=v.base.digest(value), schema_ids=ids, validation_task_id="heldout",
                   artifact_sha256="a", scorer_evidence_sha256="s", journal_sha256="j", passed=True,
                   admission_kind="retrieval_execution_contract_v1",
                   retrieval_policy_sha256=v.frozen_policy()["policy_sha256"])


def test_direct_public_transfer_injects_only_safe_terminal_slice():
    value = state(("one", schema("one")))
    query = v.derive_task_query("Send $427 on Venmo to Anita.", "appworld", meta(), registry())
    guidance, provenance = v.retrieve(value, query, registry(), admission(value, ["one"]))
    assert guidance
    assert "apis.venmo.create_transaction" in guidance
    assert "apis.phone.search_contacts" not in guidance
    assert "unproven prerequisites" in guidance
    assert provenance["selected_schema_id"] == "one"
    assert provenance["selection_decision"] == "admitted_safe_terminal_slice"


def test_account_or_payment_request_cannot_masquerade_as_transfer():
    value = state(("one", schema("one")))
    for instruction in (
        "Make a Venmo account for my parents using their email address.",
        "Make new Venmo payment requests with the corrected amount.",
    ):
        query = v.derive_task_query(instruction, "appworld", meta(), registry())
        guidance, provenance = v.retrieve(value, query, registry(), admission(value, ["one"]))
        assert guidance == ""
        assert provenance["selected_schema_id"] is None


def test_past_venmo_mention_cannot_create_transfer_guidance():
    value = state(("one", schema("one")))
    query = v.derive_task_query(
        "I paid someone on Venmo yesterday. Record that payment in Splitwise.",
        "appworld", meta(), registry(),
    )
    guidance, provenance = v.retrieve(value, query, registry(), admission(value, ["one"]))
    assert guidance == ""
    assert provenance["selected_schema_id"] is None


def test_cross_app_instruction_and_unadmitted_schema_fail_closed():
    value = state(("one", schema("one")))
    phone_meta = {"app_descriptions": {"phone": "public"}, "public_operation_intents": intents()}
    query = v.derive_task_query("Send $427 to Anita on phone.", "appworld", phone_meta, registry())
    guidance, provenance = v.retrieve(value, query, registry(), admission(value, ["one"]))
    assert guidance == ""
    assert provenance["candidate_scores"][0]["rejection_reason"] == "terminal_app_not_publicly_relevant"


def test_indistinguishable_admitted_schemas_abstain_without_id_tie_breaking():
    value = state(("z", schema("z", prior=False)), ("a", schema("a", prior=False)))
    query = v.derive_task_query("Send $427 on Venmo to Anita.", "appworld", meta(), registry())
    guidance, provenance = v.retrieve(value, query, registry(), admission(value, ["a", "z"]))
    assert guidance == ""
    assert provenance["selection_decision"] == "semantic_tie_abstention"
    assert provenance["semantic_winner_candidate_ids"] == ["a", "z"]


def test_persisted_provenance_reproduces_and_tampering_fails_closed():
    value = state(("one", schema("one", prior=False)))
    query = v.derive_task_query("Send $427 on Venmo to Anita.", "appworld", meta(), registry())
    signed = admission(value, ["one"])
    guidance, provenance = v.retrieve(value, query, registry(), signed)
    persisted = json.loads(json.dumps(provenance, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    assert v.reproduce_retrieval(value, query, registry(), persisted, signed) == guidance
    persisted["guidance"] = "changed"
    with pytest.raises(ValueError, match="does not reproduce"):
        v.reproduce_retrieval(value, query, registry(), persisted, signed)






def test_admitted_schema_survives_dynamic_enclosing_bank_update():
    value = state(("one", schema("one", terminal="apis.venmo.create_transaction")))
    signed = admission(value, ["one"])
    changed = state(("one", schema("one", terminal="apis.venmo.create_transaction")), ("later", schema("later", terminal="apis.venmo.create_transaction")))
    q = v.derive_task_query("Send money on Venmo to a user.", "appworld", meta(), registry())
    guidance, provenance = v.retrieve(changed, q, registry(), signed, admission_bank_sha256=signed["bank_sha256"])
    assert "apis.venmo.create_transaction" in guidance
    assert provenance["pre_state_semantic_sha256"] != signed["bank_sha256"]
    assert v.reproduce_retrieval(changed, q, registry(), provenance, signed, admission_bank_sha256=signed["bank_sha256"]) == guidance


