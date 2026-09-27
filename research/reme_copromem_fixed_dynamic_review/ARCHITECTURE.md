# Architecture

`copromem` core (`bank`, `contracts`, `schema`, `decomposition`,
`copromem_memory_module`, `pattern_separation`, and `types`) is reusable
library code. It is intentionally retained at `src/copromem/`.

`copromem.benchmarks.appworld` owns the AppWorld adapter, acquisition gate,
and JSON-lines native worker boundary. `copromem.benchmarks.webarena` owns
WebArena benchmark integration, loading, and evaluation. Neither boundary
vendors its benchmark.

`copromem.integrations.reme` is the official-upstream ReMe compatibility
boundary: bank construction/cloning, Fixed/Dynamic lifecycle, service process,
locked transport, and upstream executor. It invokes a separately pinned ReMe
checkout; that external source is not vendored here.

`copromem.integrations.reasoning_bank` is the importable ReasoningBank adapter.
Root `integrations/reasoning_bank/` contains the pinned external-checkout patch,
setup, and benchmark launch assets. `vendor/agent-workflow-memory/` remains an
unchanged external baseline and is not part of CoProMem or ReasoningBank code.

`copromem.experiments.reme_copromem` contains five-arm orchestration, explicit
frozen-input configuration, strict JSON support, and reporting.
It is experiment code, not a generic memory algorithm.
