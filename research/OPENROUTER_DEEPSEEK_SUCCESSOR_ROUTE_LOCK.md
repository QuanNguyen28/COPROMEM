# OpenRouter DeepSeek successor-route lock

Status: **validated for routing and native tool calling; no successor pilot dispatched.**

The one corrected canary is append-only at
`artifacts/research/reme_copromem_comparison/openrouter_deepseek_successor_canary_corrected/`.
Its result SHA-256 is
`e58bbd2d6d4359b2aeb2520963b51b3104737a72a5ce771691b2b6159fa3ac1`.

## Locked route controls

- Endpoint: `https://openrouter.ai/api/v1/chat/completions`
- Requested model: `deepseek/deepseek-v4.1-flash`
- Provider routing: `provider.only: ["deepseek"]`,
  `provider.allow_fallbacks: false`, `provider.require_parameters: true`
- Non-streaming; `reasoning_effort: "none"`
- One native function tool with the frozen `{"status":"ok"}` object schema;
  voluntary `tool_choice: "auto"`; no forced function selection and no
  `parallel_tool_calls` request parameter.
- No fallback model, provider substitution, retries, or background calls.

## Canary evidence

The provider-reported response was HTTP 200, model
`deepseek/deepseek-v4.1-flash`, resolved provider `DeepSeek`, finish reason
`tool_calls`, exactly one valid `{"status":"ok"}` call, zero reasoning tokens
and no reasoning content. It used 286 prompt tokens and 37 completion tokens,
took 1.771 seconds, and reported USD 0.00006510 actual cost. The USD 0.01
reservation was settled to that actual cost.

The preceding incompatible canary remains immutable with its USD 0.01 retained
reservation; this corrected canary is its append-only successor.

## Completion limit

The canary itself used 128 completion tokens to stay well within its USD 0.01
reservation. The successor pilot's independently preregistered executor ceiling
remains **1024 completion tokens uniformly for every acquisition, lifecycle,
and evaluation model call**, based on the earlier provider-neutral truncation
audit. The canary validates the route/tool protocol, not a 1024-token response.
No task manifest or pilot run has been created from this record.
