#!/usr/bin/env python3
"""Zero-cost fixture for append-only verified CoProMem response cache fields."""
from __future__ import annotations
import hashlib, json, tempfile
from pathlib import Path
from research.official_pilot.strict_copromem_json import extract

def main() -> None:
    raw = 'prefix ```json\n{"is_compound":true,"rationale":"fixture"}\n``` suffix'
    parsed, accepted, span = extract("copromem_complexity_v1", raw, "stop", False)
    request = hashlib.sha256(b"exact-config").hexdigest()
    record = {"request_digest":request,"schema_name":"copromem_complexity_v1",
              "raw_response_sha256":hashlib.sha256(raw.encode()).hexdigest(),"accepted_object":accepted,
              "object_span":list(span),"parsed_object":parsed}
    with tempfile.TemporaryDirectory() as root:
        path=Path(root)/"cache.jsonl"; path.write_text(json.dumps(record)+"\n",encoding="utf-8")
        stored=json.loads(path.read_text(encoding="utf-8")); replay, exact, _=extract(stored["schema_name"],stored["accepted_object"],"stop",False)
        assert replay == stored["parsed_object"] and exact == stored["accepted_object"] and stored["request_digest"] == request
    print("copromem_response_cache_fixture=passed")
if __name__ == "__main__": main()
