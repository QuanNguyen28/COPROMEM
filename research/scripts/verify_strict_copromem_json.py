#!/usr/bin/env python3
from research.official_pilot.strict_copromem_json import StrictJSONError, extract, parse

def rejects(text, reason="stop"):
    try: parse("copromem_complexity_v1", text, reason, False)
    except StrictJSONError: return
    raise AssertionError(text)

def main():
    assert parse("copromem_complexity_v1", '{"is_compound":true,"rationale":"x"}', "stop", False)["is_compound"]
    value, raw, span = extract("copromem_complexity_v1", '```json\n{"is_compound":true,"rationale":"x"}\n```', "stop", False)
    assert raw == '{"is_compound":true,"rationale":"x"}' and span[0] > 0 and value["is_compound"]
    assert parse("copromem_complexity_v1", 'note: {"is_compound":true,"rationale":"x"} thanks', "stop", False)["is_compound"]
    for bad in ('{"is_compound":true,"rationale":"x"}{"is_compound":false,"rationale":"y"}', '', '{"is_compound":'):
        rejects(bad)
    rejects('{"is_compound":true,"is_compound":false,"rationale":"x"}')
    rejects('{"is_compound":true,"rationale":"x"}', "length")
    print("strict_copromem_json_format_regression=passed")
if __name__ == "__main__": main()
