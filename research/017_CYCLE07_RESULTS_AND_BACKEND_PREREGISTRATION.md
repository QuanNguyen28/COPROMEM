# Cycle 7 decision and cycle 8 preregistration

Recorded 2026-09-16 after the complete cycle-7 audit, before any cycle-8 paid
generation. Branch `codex/copromem-research-loop`; HEAD remains
`18025102c010e85f26b0b3fb1144a1cb684b587e`. Original documents and all earlier
records are preserved. No commit or push.

## Cycle 7: observed result

Decision: **REVISE** source collection; the revised interface is insufficient to
support same-task outcome-contrast induction with the current backend/horizon.

All eight registered episodes ran their full 15-step horizon. Native success was
0/8, the primary metric was zero mixed-outcome scenarios, and all eight independent
replays matched tested state, public history and native score. No native scorer
was changed, and all saved database hashes remained unchanged by evaluation.

| Diagnostic | Cycle 6 | Cycle 7 |
|---|---:|---:|
| Native task successes | 0/8 | 0/8 |
| Mixed-outcome scenarios | 0/4 | 0/4 |
| Recorded action errors | 113/120 | 56/120 |
| AST parsing failures | 91/120 | 2/120 |
| Programs without an AST call expression | 11/120 | 0/120 |
| Steps containing literal API call sites | 18/120 | 118/120 |
| Generations stopped at token cap | 10/240 | 0/240 |
| Settled external-model cost, USD | 0.06122978 | 0.05485080 |

These cross-cycle differences are descriptive, **not checkpoint-locked causal
effects**. Two interface changes were bundled, prompts/generations differ, and
remote stochasticity remains. Neither row is a learned-memory treatment.

In cycle 7 all 120 planner outputs parsed without fallback; 57 executor outputs
needed explicit fence/JSON compatibility parsing. That fallback category is not
directly comparable to cycle 6's JSON-string parsing failure rate. All 240 model
generations reported normal stop. Observed errors now include nonexistent API
names, missing login parameters, invalid simulated credentials, incorrect
list/dictionary handling and repeated unproductive discovery. Better syntax was
not sufficient for actual task completion.

Native check counts were identical to cycle 6: both replicates passed 1/2 checks
on 27e1026_1, 1/4 on b7a9ee9_1, 0/7 on 60d0b5b_1, and 1/4 on aa8502b_1. Those
fractions are not fractional task success. None raised the completion flag.

Usage: 927,406 prompt tokens, 13,934 completion tokens, 941,340 total tokens;
240 completed calls and 240 HTTP attempts, no unsettled attempts. Archived
provider charges reconcile to USD 0.05485080. Total paid research through this
cycle: 678 completed calls, 680 attempts, USD 0.12123675 settled and
USD 0.12229725 charged/reserved. The difference is still cycle 3's two ambiguous
attempts. Local compute has not been monetized.

Evidence root: `artifacts/research/cycle07_appworld_source`.

- Collection: `reports/4b2401850356972cea663dca3449216dea5cd81e980387c4d5c31094dd638be2.json`.
- Complete audit: `source_audits/4370b6d5699032d2e0b2914496ae28327a9a5656f49a6afd38d2cc6735f464bf.json`.
- Exact source/configuration, generations, live frames, final-prefix replay,
  native evaluations, usage and reservations remain in the immutable store.

The strongest competing explanations are limited model capability, inadequate
workflow/horizon or remaining context/adapter restrictions. This result does not
show that stateful procedural memory is impossible. It does show that syntax
repair alone cannot be presented as the scientific contribution, and this source
corpus still supplies no successful/failed episode pairs.

## Cycle 8: prospectively fixed backend-sensitivity test

Question: with the now-executable common interface held fixed, does a different,
larger instruction model supply usable native outcome contrasts?

Model: `qwen/qwen3-30b-a3b-instruct-2507`, pinned provider `nebius/fp8`.
This is a model **and provider/precision** sensitivity test, not an isolated
parameter-count causal experiment. The instruction model is selected as a
plausible stronger coding/tool-use backend; superiority on these tasks is a
hypothesis, not a verified fact. No model outputs were sampled to choose it.

The unauthenticated OpenRouter model-endpoint metadata was retrieved and saved in
`artifacts/research/backend_screen_20260916/metadata` before paid calls. The chosen
route advertises seed, temperature and token-cap support, with input/output prices
of USD 0.10/0.30 per million tokens at inspection. Those fit the transport's fixed
USD 0.25/0.50 per-million price ceilings. Metadata is refreshed into the new run
store. Fallback routing remains disabled. Seed support is not determinism proof.

Freeze all other scientific settings from cycle 7: public-onboarding-v2, raw Python
executor output, fixed two-role team, the same four build scenarios, two
replicates, 15 steps, environment seed 100, model seed schedule 61, 384/768 output
token caps and 24,000-character public context. Same immutable AppWorld image,
native evaluator, shared action policy and paired replay validation. No adaptive
team/model routing, extra recovery, memory, hidden solutions or outcome-based
task selection. Reserved partitions stay unopened; the oracle scenario remains
excluded.

Config: `research/configs/cycle08_appworld_source.json`.
Store: `artifacts/research/cycle08_appworld_source`.
Use a new namespace and episode prefix. Budget: USD 0.25 and 300 HTTP attempts,
including retries/reserved failures. At most 240 completed generations. Stop on
recorded provider or infrastructure failure; do not silently substitute a route,
model or task. Source snapshots are written before the first paid generation.

Primary metric remains number of scenarios with both a native-success and
native-failure eligible episode. Zero mixed scenarios rejects this protocol as
sufficient input to same-task outcome-contrast induction. Separately report total
successes, all local errors, replay/unsupported-state failures and cost. An all-
success sample still lacks negative contrast; an all-failure sample still lacks
positive contrast. Neither should be replaced with hand-designed labels.

If successes appear but no mixed pairs do, prospectively consider source diversity
or additional replications instead of selective reruns. If actual public tool use
still cannot solve tasks, inspect fixed workflow/context/horizon constraints before
spending on memory arms. If usable contrasts appear, proceed to build-only public
defect analysis and exact environment-plus-artifact checkpoints; candidates still
need independent static/equal-compute-controlled effect validation and admission.

No cross-cycle improvement may be called learned-contract gain, and no apparent
backend difference is a main-study generalization or significance result. The
full research objective remains open.
