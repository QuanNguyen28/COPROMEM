# Cycle 8 results and cycle 9 coding-backend preregistration

Recorded 2026-09-16, after the complete cycle-8 audit and before any cycle-9 paid
generation. Branch `codex/copromem-research-loop`, unchanged HEAD
`18025102c010e85f26b0b3fb1144a1cb684b587e`. Earlier protocols, raw evidence and
original documents are retained. No commit or push.

## Observed cycle-8 result

Decision: **REVISE** the source protocol. The preregistered primary metric remains
zero mixed-outcome scenarios (0/4): all eight native episodes failed. All eight
independent prefix replays and native evaluations match, with no unsupported-state
or provider failure. The native scorer and saved databases were not changed by
evaluation. No learned contract was proposed, admitted or tested in this cycle.

| Diagnostic | Cycle 7: Ministral 3B | Cycle 8: Qwen 30B-A3B |
|---|---:|---:|
| Native success | 0/8 | 0/8 |
| Mixed-outcome scenarios | 0/4 | 0/4 |
| Completed steps | 120 | 120 |
| Recorded local action errors | 56 | 35 |
| AST parsing failures | 2 | 0 |
| Planner parsing fallbacks | 0 | 0 |
| Executor formatting fallbacks | 57 | 0 |
| Token-cap finishes | 0/240 | 0/240 |
| Settled model cost, USD | 0.05485080 | 0.09919890 |

Every cycle-8 step contains a literal API call site, but this is not proof that
the intended call executed or that the task progressed. The public traces show
repeated discovery, passwords confused with access tokens, guessed identities,
missing token arguments even after login, and repeated rejected operations.
These are retrospective descriptions, not gold causal labels for handoffs.

Native check counts remain 1/2 on 27e1026_1, 1/4 on b7a9ee9_1, 0/7 on 60d0b5b_1,
and 1/4 on aa8502b_1 for both replicates. Partial check counts are not fractional
task success. No episode set the completion flag. All ran the 15-step horizon.

Usage: 957,504 prompt and 11,495 completion tokens, 968,999 total; 240 completed
calls and 240 HTTP attempts, no unsettled attempts. Raw usage reconciles to
USD 0.09919890. Cumulative through cycle 8: 918 completed calls, 920 attempts,
USD 0.22043565 settled and USD 0.22149615 charged/reserved. The difference remains
cycle 3's two ambiguous attempts. Local computation is not monetized.

Evidence root: `artifacts/research/cycle08_appworld_source`.

- Collection report: `reports/9e632b4c146c9193a2785101ce55e2efb3b44601e3ef80b389704368c12cd870.json`.
- Complete offline audit: `source_audits/9cf0b5124942ffec2673904e71b8efaf23ba9f83e24d2b1bb2d9d317f56f9961.json`.
- Source snapshots, effective model requests, public frames, independent worker
  outputs, native evaluations and budget entries remain immutable.

The strongest alternatives remain baseline capability, restrictive context or
step budget, and fixed planner/executor coordination quality. Zero success does
not establish that AppWorld is unsolvable or that procedural learning is useless.
Cross-cycle differences are not checkpoint-locked causal estimates. Temperature
zero and provider seed support do not prove backend determinism.

## Cycle 9: frozen stronger-coding-backend diagnostic

Hypothesis: a code-specialized backend can use the existing public interface well
enough to yield native successes and possibly mixed same-task outcome evidence.
Falsification: zero mixed-outcome scenarios rejects the sufficiency of this
specific source protocol; zero success especially requires revisiting the common
workflow before any memory-arm experiment. All-success episodes would also lack
negative contrast. Do not selectively replace scenarios or replications.

Model: `qwen/qwen3-coder`; route: `deepinfra/turbo`. The
[official model card](https://huggingface.co/Qwen/Qwen3-Coder-480B-A35B-Instruct)
describes a non-thinking code-specialized mixture with 480B total/35B active
parameters. This motivates the selection; it does not demonstrate superiority on
our tasks. We retain temperature zero and short per-step output caps for this
sensitivity test, not the card's recommended long-output/sampling recipe.

Unauthenticated [endpoint metadata](https://openrouter.ai/api/v1/models/qwen/qwen3-coder/endpoints)
was saved under `artifacts/research/backend_screen_20260916/metadata`, without
sampling model outputs to select the backend. At inspection the route advertises
FP4, seed/temperature/token-cap support and input/output prices of USD 0.30/1.00
per million tokens. Pricing and remote weights are not immutable; the new store
refreshes metadata and records response model identifiers/fingerprints where
available. This changes model, provider and precision, not parameter count alone.

Preserve cycle 8's exact scientific settings: four build scenarios, first variant,
two replicates, seed schedule 61, environment seed 100, 15 steps, 384/768 planner/
executor output tokens, 24,000-character public context, public-onboarding-v2,
raw Python, same immutable worker image, action restrictions, evaluator and replay
eligibility. Fixed team with no memory or adaptive routing. No hidden solutions,
test cases, native database internals or reserved-partition instructions are given
to either agent. Entire diagnostic/oracle scenario 07b42fd remains excluded.

Config: `research/configs/cycle09_appworld_source.json`.
Store: `artifacts/research/cycle09_appworld_source`.

Budget USD **1.00**, within the user's USD 5 per-cycle authorization; maximum
300 HTTP attempts and at most 240 completed generations. Provider price ceilings
are USD 0.50 input and 2.00 output per million. The runner now accepts declared
finite positive ceilings and passes them both to the route filter and to the
pre-attempt conservative budget reservation. Old configurations retain 0.25/0.50
defaults. Changing the price filter is not extra task knowledge. All 137 unit
tests pass, including new rejection/default/forwarding tests; Ruff passes.

Stop and record infrastructure/provider failures; do not silently change route,
budget, task or prompts. Existing interrupted live episodes require explicit
audited recovery. Source/configuration snapshots are frozen before paid calls.

The primary metric remains the count of native mixed-outcome build scenarios.
Report all successes, errors, replay results, token/call totals and monetary cost.
No significance claim, population superiority, learned gain, benchmark
generalization or submission readiness follows from this small source run.

If usable contrasts appear, analyze build-only public defects and construct exact
environment-plus-planner-artifact intervention checkpoints. Any candidate must
then survive separate effect validation, static and equal-compute controls, and
disjoint admission/evaluation. If they do not appear, audit horizon/context and
fixed-team restrictions rather than scaling a weak-baseline comparison grid.
