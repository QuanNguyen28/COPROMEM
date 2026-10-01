from copromem.integrations.reasoning_bank.appworld_protocol import protocol_record, validate_protocol


def test_protocol_is_frozen_and_self_judge_is_separate_from_official_score():
    value = protocol_record()
    validate_protocol(value)
    assert value["appworld_official_scorer_used_for_memory_label"] is False
    assert value["judge_temperature"] == 0.0
    assert value["extractor_temperature"] == 1.0
    assert value["retrieval"]["k"] == 1
    assert value["embedding"] == {
        "model": "openai/text-embedding-3-small", "provider": "azure",
        "transport": "OpenRouter", "dimensions": 1024, "encoding_format": "float",
        "provider_fallback": False, "normalization": "unit_l2_before_cosine",
        "transport_identity": "copromem.integrations.reme.transport.LockedEmbeddings",
    }
