from __future__ import annotations

import copy

import pytest

from copromem.experiments.reme_copromem import task_conditioned_retrieval_v627 as v
from copromem.experiments.reme_copromem.public_operation_intent_registry import digest, _tokens
from copromem.experiments.reme_copromem.schema_external_admission import receipt
from copromem.experiments.reme_copromem.schema_multi_admission import bundle, schema_identity


def registry():
    return {
        "registry_sha256": "r",
        "normalization": {"operation_aliases": {}},
        "operations": [
            {"operation": "apis.venmo.create_transaction", "http_method": "POST", "access_mode": "write"},
            {"operation": "apis.phone.send_text_message", "http_method": "POST", "access_mode": "write"},
        ],
    }


def intents():
    value = {"version": "appworld-public-operation-intent-registry-v1", "sources": [], "operations": [
        {"operation": "apis.venmo.create_transaction", "app": "venmo", "http_method": "POST",
         "description": "Send money to a user.", "description_tokens": _tokens("Send money to a user.")},
        {"operation": "apis.phone.send_text_message", "app": "phone", "http_method": "POST",
         "description": "Send a text message.", "description_tokens": _tokens("Send a text message.")},
    ]}
    value["operations"].sort(key=lambda row: row["operation"])
    value["intent_registry_sha256"] = digest(value)
    return value


def meta(*apps: str):
    return {"app_descriptions": {app: "public" for app in apps}, "public_operation_intents": intents()}


def schema(terminal: str):
    return {
        "policy_version": "copromem-v6.1-semantic-graph-v1", "registry_sha256": "r",
        "required_operations": [terminal], "terminal_effect": terminal,
        "terminal_occurrence_id": f"{terminal}#1",
        "typed_constraints": [{"operation": terminal, "occurrence_index": 1,
                               "required": ["body"], "outputs": ["result"]}],
        "support": {"successes": 2},
    }


def state(**rows):
    return {"contrastive_v6_schemas": rows}


def admitted(value):
    rows = []
    for schema_id, item in value["contrastive_v6_schemas"].items():
        external = receipt(bank_sha256="source-" + schema_id, schema_ids=[schema_id],
            validation_task_id="held-" + schema_id, artifact_sha256="a", scorer_evidence_sha256="s",
            journal_sha256="j", passed=True, admission_kind="retrieval_execution_contract_v1",
            retrieval_policy_sha256=v.frozen_policy()["policy_sha256"])
        rows.append({"schema_id": schema_id, "schema_identity_sha256": schema_identity(item),
                     "external_admission_receipt": external})
    return bundle(policy_sha256=v.frozen_policy()["policy_sha256"], entries=rows)


def test_multiple_independently_admitted_apps_retrieve_only_same_app_terminal():
    value = state(venmo=schema("apis.venmo.create_transaction"), phone=schema("apis.phone.send_text_message"))
    query = v.derive_task_query("Send a text message using Phone.", "appworld", meta("phone"), registry())
    guidance, provenance = v.retrieve(value, query, registry(), admitted(value))
    assert "apis.phone.send_text_message" in guidance
    assert "apis.venmo.create_transaction" not in guidance
    assert provenance["selected_schema_ids"] == ["phone"]
    assert v.reproduce_retrieval(value, query, registry(), provenance, admitted(value)) == guidance


def test_equivalent_slices_render_without_schema_id_tiebreaking():
    value = state(a=schema("apis.phone.send_text_message"), z=schema("apis.phone.send_text_message"))
    query = v.derive_task_query("Send a text message using Phone.", "appworld", meta("phone"), registry())
    guidance, provenance = v.retrieve(value, query, registry(), admitted(value))
    assert guidance
    assert provenance["selected_schema_id"] is None
    assert provenance["selected_schema_ids"] == ["a", "z"]
    assert provenance["selection_decision"] == "admitted_exact_safe_terminal_slice"


def test_distinct_safe_terminals_abstain_without_schema_order_tiebreaking():
    value = state(a=schema("apis.phone.send_text_message"), z=schema("apis.venmo.create_transaction"))
    query = v.derive_task_query("Send a message on Phone and transfer money with Venmo.", "appworld", meta("phone", "venmo"), registry())
    guidance, provenance = v.retrieve(value, query, registry(), admitted(value))
    assert guidance == ""
    assert provenance["selection_decision"] == "semantic_tie_abstention"


def test_changed_live_schema_or_v626_receipt_fails_closed():
    value = state(phone=schema("apis.phone.send_text_message"))
    admission = admitted(value)
    changed = copy.deepcopy(value)
    changed["contrastive_v6_schemas"]["phone"]["typed_constraints"][0]["required"] = ["different"]
    query = v.derive_task_query("Send a text message using Phone.", "appworld", meta("phone"), registry())
    with pytest.raises(ValueError, match="semantic identity differs"):
        v.retrieve(changed, query, registry(), admission)
    incompatible = copy.deepcopy(admission)
    incompatible["retrieval_policy_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="bundle hash mismatch"):
        v.retrieve(value, query, registry(), incompatible)


def test_mutable_support_count_can_grow_without_changing_admitted_terminal_slice():
    value = state(phone=schema("apis.phone.send_text_message"))
    admission = admitted(value)
    updated = copy.deepcopy(value)
    updated["contrastive_v6_schemas"]["phone"]["support"]["successes"] = 9
    query = v.derive_task_query("Send a text message using Phone.", "appworld", meta("phone"), registry())
    guidance, provenance = v.retrieve(updated, query, registry(), admission)
    assert guidance
    assert provenance["selected_schema_ids"] == ["phone"]


def test_missing_or_reordered_admission_entry_fails_closed():
    value = state(a=schema("apis.phone.send_text_message"), z=schema("apis.venmo.create_transaction"))
    admission = admitted(value)
    query = v.derive_task_query("Send a text message using Phone.", "appworld", meta("phone"), registry())
    missing = copy.deepcopy(admission)
    missing["entries"] = missing["entries"][:1]
    missing["bundle_sha256"] = v.base.digest({key: item for key, item in missing.items() if key != "bundle_sha256"})
    # A smaller valid bundle is permitted but cannot silently substitute a
    # reordered receipt or a live schema that was not independently admitted.
    v.retrieve(value, query, registry(), missing)
    reordered = copy.deepcopy(admission)
    reordered["entries"].reverse()
    reordered["bundle_sha256"] = v.base.digest({key: item for key, item in reordered.items() if key != "bundle_sha256"})
    with pytest.raises(ValueError, match="unordered or duplicated"):
        v.retrieve(value, query, registry(), reordered)
