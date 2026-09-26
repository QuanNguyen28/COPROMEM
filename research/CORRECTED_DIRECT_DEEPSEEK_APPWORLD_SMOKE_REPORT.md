# Corrected exposure-labelled AppWorld smoke report

Status: **NO-GO for the USD 35 efficacy pilot.** The corrected acquisition
gate stopped the run before evaluation, as registered. This is a plumbing and
lifecycle-separation result only; it is not an efficacy, ranking, transfer, or
generalization result.

## Route and manifest

* Route: official direct DeepSeek Chat Completions API; model
  `deepseek-flash`; non-thinking (`reasoning_effort: none`); native strict
  `execute_python` tool; no fallback, streaming, or model substitution.
* Source pin: `6eca54ca14a7935fcdcdc1a9a77319ed113a0679`.
* Corrected manifest SHA-256:
  `485c7ddf44b27a8614852d9fe31561088151b807c53c34c7c4bdc81c7267431b`.
* Previous exposed plumbing run remains immutable and invalid for comparison.

## Acquisition integrity

Every acquisition action has a write-once planned-action record and a native
action record before another model dispatch. Both trajectories have complete
ten-action traces, official scores, and frozen raw-trace hashes:

| Task | Official score | Trace SHA-256 | Calls | Prompt / completion tokens | Valid tools | Latency | USD |
|---|---:|---|---:|---:|---:|---:|---:|
| `50e1ac9_1` | 1 / 2 | `486fea60621e4efc44abac102e2513cf6b37e64dc1450e3753ff6cac30baec18` | 10 | 12,861 / 549 | 10 / 10 | 11.092 s | 0.0045171 |
| `50e1ac9_2` | 1 / 2 | `5809bd1737e474b8a2234b49e8b4f8e93fd71f7a5ccbd977996a27142b3a71ba` | 10 | 27,971 / 526 | 10 / 10 | 11.089 s | 0.0090225 |

Both official scores are unsuccessful. Consequently there is no successful
source trajectory from which ReMe fixed/dynamic or CoProMem v2 may construct
provenance-bound memory. The gate correctly rejected evaluation with:
`no successful acquisition can produce a provenance-bound memory`.

No evaluation model call or scored evaluation occurred. No placeholder, generic failure text,
or fabricated memory was injected. Therefore no distinct ReMe/CoProMem memory
text exists to report. ReMe remains a **faithful lifecycle adaptation**, not a
direct upstream reproduction.

## Ledger and artifact integrity

* Historical carried attempts/exposure: 56 / USD 0.06416778.
* Corrected new attempts: 20; all reservations settled: 20 / 20.
* All-in exposure: **USD 0.07770738 / USD 1.00**.
* Corrected total attempts: 76 (historical plus corrected); no unregistered
  model calls or evaluation calls are recorded.
* Raw native outputs are not persisted; action source plus output digest/status
  provides the trace while protecting task-private state.
* Result SHA-256: `c31692c0e700c836512314330058d8c9fb119222b124240f68d64a564d67259a`.

## Bug fixes verified

The original loss was caused by end-only result persistence. The corrected
runner uses write-once action plans, action outcomes, official-score records,
and telemetry records. Its acquisition gate rejects missing score/trace,
generic memory, missing method provenance, and identical ReMe/CoProMem memory.
The deterministic regression suite (ledger, journal, adapters, native-smoke
contract, and direct transport) passed **26 / 26**. The authorized native
zero-model AppWorld fixture passed its official 2 / 2 scorer check.
