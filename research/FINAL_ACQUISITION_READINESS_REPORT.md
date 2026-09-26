# Final 30-action acquisition-readiness result

Decision: **NO-GO.** The current executor/acquisition configuration is
incompatible with establishing the required successful source pool. Do not
launch a corrected evaluation smoke or the USD 35 efficacy pilot with this
configuration. Change the executor model, acquisition source, or benchmark
design before a future efficacy proposal.

This run used the originally intended 30-action ceiling, not a change to the
official 2/2 criterion. Both tasks were explicitly development/exposed.

## Provider-neutral preflight

The five invalid outcomes in the preceding readiness run were all exact
128-token completion truncations (`finish_reason=length`), with the expected
model identity. No schema or serialization failure was found. The only changes
were provider-neutral: completion ceiling 128 → 256 and bounded serialized
native feedback (3,000 characters). The strict native tool schema, route,
model, non-thinking mode, action criterion, and common documented-API contract
were unchanged.

## Official acquisition outcomes

| Task | Seed | Action limit | Official score | Calls | Prompt / completion tokens | Valid tools | Latency | USD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `50e1ac9_1` | 404 | 30 | 1 / 2 | 17 | 72,498 / 2,036 | 16 / 17 | 23.711 s | 0.0241926 |
| `50e1ac9_2` | 404 | 30 | 1 / 2 | 4 | 6,496 / 567 | 3 / 4 | 5.230 s | 0.0026292 |
| **Total** | — | — | **0 / 2 successes** | **21** | **78,994 / 2,603** | **19 / 21** | **28.941 s** | **0.0268218** |

Both trajectories ended with an exact 256-token truncation after their valid
tool calls. Their write-once action plans, native action records, official
scores, trace hashes, and provenance are preserved. No hidden checker/state was
inspected and no task-specific hint, authored solution, generic memory, or
evaluation call was used.

## Ledger and lifecycle decision

The ledger carried 102 prior attempts and USD 0.11080818, then settled all 21
new calls. All-in exposure is **USD 0.13762998 / USD 1.00**. The frozen final
manifest SHA-256 is
`27e575e9312bd330d84345a227f1fd50f753848b6008d410005e3a8d031d4ec0`; result
SHA-256 is
`57157571103f3b6fbf001178e60b4db83bfbe966f3e0b4138574755c109c08aa`.

Neither task met official 2/2. Therefore no valid source pool exists, no ReMe
or CoProMem lifecycle output was built, and no separate corrected evaluation
smoke is warranted. ReMe remains a faithful adaptation, not direct upstream
execution.
