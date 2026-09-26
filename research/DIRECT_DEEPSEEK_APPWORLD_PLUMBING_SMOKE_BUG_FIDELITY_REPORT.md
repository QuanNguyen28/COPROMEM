# Direct DeepSeek AppWorld Plumbing Smoke — Bug/Fidelity Report

Status: **STOPPED BEFORE SMOKE**. This is an exposure-labelled plumbing
attempt only; it makes no efficacy, ranking, transfer, superiority, or
generalization claim.

## Route and canary

- Requested direct route: https://api.deepseek.com/chat/completions
- Requested model: deepseek-flash; model fallback disabled by using the
  direct, exact-model endpoint only.
- Reasoning control in the request: reasoning_effort: "none".
- One minimal tool plus JSON-schema structured-output canary was authorized.
- The API key was sourced only in process from .env; it was not printed,
  serialized, committed, or included in artifacts.
- Before dispatch, the append-only shared ledger reserved USD 0.01. There is
  no retry path.

The one network attempt failed with HTTPError. Consequently there is no
verified response model, completion reason, tool call, JSON arguments,
structured output, usage, reasoning-token count, latency, or actual provider
charge. The runner correctly stopped and did not start the AppWorld smoke.

## Budget and artifacts

- Shared ceiling: USD 1.00 and 78 registered requests.
- Ledger exposure after the failure: USD 0.01108768 charged-or-reserved.
- The USD 0.01 failed-canary reservation is deliberately retained, so an
  ambiguous provider outcome cannot be reused.
- Redacted route/reservation record:
  artifacts/research/reme_copromem_comparison/openrouter_brokered_smoke/direct_deepseek_canary_role/1790320831825016000.json
- Redacted transport record:
  artifacts/research/reme_copromem_comparison/openrouter_brokered_smoke/direct_deepseek_canary_transport/1790320831825016000.json

No acquisition, persistence, retrieval, prompt/tool-parity, AppWorld scoring,
or smoke artifacts were generated. No AppWorld task was executed.

## Bug/fidelity finding

The original direct-canary transport handler recorded only HTTPError type, not
a redacted HTTP status or error class/code. The existing retained response has
no additional locally available status, request ID, or body, so its exact
failure category is not recoverable without repeating the prohibited request.

This diagnostic deficiency is now corrected in
src/copromem/direct_deepseek_transport.py. It allow-lists only status, provider
error code/type, request ID, and a redacted/truncated message; it never records
authorization, cookies, API keys, request bodies, or other response headers.
Deterministic fixtures cover 400, 401, 402, 404, 422, 429, and 503 responses.

For a future separately authorized canary, the request should retain
reasoning_effort none, remove the unsupported json_schema response_format
field, and put strict true on the function tool definition. The maximum
pre-dispatch reservation remains USD 0.01. A new paid canary would require
explicit authorization because the approved one has already been consumed.
