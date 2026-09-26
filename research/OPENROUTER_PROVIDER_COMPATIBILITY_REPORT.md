# OpenRouter provider compatibility report: DeepSeek V4.1 Flash canaries

## Status: stopped; no plumbing smoke executed

This is an OpenRouter-brokered compatibility check, not a direct DeepSeek API
reproduction and not a method comparison. All requests used the exact model
`deepseek/deepseek-v4.1-flash`, one pinned provider at a time,
`allow_fallbacks=false`, `reasoning_effort=none`, a 16-token limit, no retry,
and the unchanged strict canary tool schema.

The zero-cost provider inventory identified `fireworks`, `deepinfra`, and
`relace` as alternatives serving the exact model. Sail Research was excluded
after its earlier malformed tool-call result.

| Order | Pinned provider | Result | Gate outcome |
| ---: | --- | --- | --- |
| 1 | Fireworks (`fireworks`) | HTTP 404: no endpoint could handle the requested parameters | failed before generation |
| 2 | DeepInfra (`deepinfra`) | exact model/provider, `finish_reason=tool_calls`, 294 prompt + 16 completion tokens, zero reasoning tokens, 1.656s, USD 0.00004788 | failed: one call carried `{}` rather than the required `{"status":"ok"}` JSON |
| 3 | Relace (`relace`) | HTTP 404: no endpoint supported the required `tool_choice` | failed before generation |

No schema was loosened and no provider was retried. The shared append-only
ledger remains below USD 1. Its charged-or-reserved exposure is USD
`0.00108768`: the previous USD `0.0003342` unresolved reservation, Fireworks
and Relace conservative reservations, and the DeepInfra settled cost.

No acquisition, evaluation, memory lifecycle, prompt/tool parity check,
official scoring, or method arm ran. Therefore this report contains no
performance, ranking, efficacy, transfer, superiority, or generalization
claim.
