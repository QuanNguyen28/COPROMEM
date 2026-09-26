# OpenRouter-brokered DeepSeek V4.1 Flash plumbing smoke: bug/fidelity report

## Status: stopped before smoke execution

Source revision: `6eca54ca14a7935fcdcdc1a9a77319ed113a0679`.

Two separately authorized canaries were dispatched; neither permitted the
plumbing smoke to start. The first used
`deepseek/deepseek-v4.1-flash`, provider-only `deepseek`,
`allow_fallbacks=false`, `reasoning_effort=none`, `max_tokens=16`, and one
transport attempt. OpenRouter returned HTTP 404 before generation: the account
privacy/guardrail policy excluded the sole matching DeepSeek endpoint for
"Paid model training violation". No retry, fallback, substitute model, task
execution, or smoke arm ran. The second used the subsequently authorized
open-provider route with the exact requested model, model fallback disabled,
and `reasoning_effort=none`. It resolved to `Sail Research`, returned the exact
model identifier, 97 prompt tokens, 2 completion tokens, zero reasoning tokens,
about 8.11 seconds latency, and USD 0 actual cost. However,
`finish_reason=error` and the only tool-call arguments were malformed (`{`).
Tool calling and structured output therefore did not work correctly.

## Recorded ledger and route evidence

The append-only artifact root is
`artifacts/research/reme_copromem_comparison/openrouter_brokered_smoke/`.
It records both route settings, the first USD `0.0003342` reservation and
HTTP-404 transport attempt, and the second canary response metadata. The second
canary settled to USD 0; the first reservation remains charged-or-reserved
exposure because it ended ambiguously before a usage record.

The reservation remains charged-or-reserved exposure; it is not released on an
ambiguous/error outcome. It is below the authorized USD 0.01 canary maximum and
the shared USD 1 ceiling. The frozen peak price snapshot was USD 0.30/M input
and USD 1.20/M output; the model catalogue returned the same base rates.

## Gates and fidelity findings

* Linux AppWorld startup and native zero-model scorer fixture passed previously
  (`82e2fac_1`, 2/2 native checks).
* The acquisition/evaluation tasks and four arms did not start. Consequently
  there are no memory, persistence, retrieval, prompt/tool parity, official
  scoring, or arm artifacts from this smoke.
* The second canary confirmed exact-model routing and zero reasoning tokens,
  but failed the tool/structured-output gate; its provider was `Sail Research`.
* The failures are OpenRouter account/configuration and response-fidelity
  issues, not AppWorld scores or method-comparison results.

No efficacy, ranking, transfer, superiority, or generalization conclusion is
permitted from this stopped plumbing attempt.
