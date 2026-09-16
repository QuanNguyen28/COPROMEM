# Cycle 6: live stateful source collection, preregistered

Recorded 2026-09-16, approximately 01:41 UTC, before any cycle-6 paid generation.
Branch `codex/copromem-research-loop`; HEAD
`18025102c010e85f26b0b3fb1144a1cb684b587e`. Source is uncommitted and will be
snapshotted in the write-once run store before paid calls. Original documents
and all older observations remain intact.

## Question and falsification

Can a small fixed planner/executor team produce replay-verifiable, mixed native
outcomes on a deterministic, scenario-disjoint selection of AppWorld training
tasks? This tests whether the proposed stateful contract direction has usable
source evidence. It does **not** test a learned contract or claim that an
unsuccessful task labels every preceding plan as defective.

Primary metric: number of build scenarios containing both a native-success and
a native-failure episode, with each recorded prefix passing the replay gate.
Zero such scenarios falsifies the sufficiency of this source protocol for
outcome-contrast induction. Unsupported state, infrastructure errors and provider
errors are recorded, never quietly excluded from the collection denominator.
Local action errors are a separate diagnostic, not a substitute for native task
success. A local error may be corrected by the ordinary baseline workflow.

The strongest alternative explanation for poor outcomes is an underpowered
model, short horizon or restricted common adapter, not impossibility of agent
memory. Conversely, mixed outcomes alone cannot establish a learnable or causal
handoff defect. Any subsequent contract must pass fresh checkpoint-locked
intervention, static-control and equal-compute comparisons.

## Engineering gate already tested

The live controller keeps one isolated worker process open for an episode.
The replay controller starts a separate fresh process with the recorded action
prefix. Both paths snapshot at the same boundaries. Typed state encoding
distinguishes list/tuple and dictionary order; tracks shared mutable references
and cycles; records supported module aliases, functions and dates. Unsupported
values cause an unverified checkpoint, not a guessed match. This is a tested
subset of Python state, not proof of arbitrary interpreter equivalence.

`artifacts/research/cycle06_runtime` contains live-a/replay-a and independent
native evaluations. The authored fixture covers an alias mutation, function,
date, set, expected invalid-API error at index 3, and random draw. Both runs have
state digest `42b5a6b9fff99770e6ba457d40898767dfa335df9112dca69dc19ff87b9f1ec6`;
the native evaluator reports failure, 1/5 checks, for both. Persisted databases
remain unchanged by evaluation. This deliberately incomplete fixture is not a
task-performance example. No model calls were used. Ruff and all 110 tests pass.

## Frozen collection design

Configuration: `research/configs/cycle06_appworld_source.json`.
Output: `artifacts/research/cycle06_appworld_source`.

- Native AppWorld `0.1.3.post1`; hash-locked Linux dependencies.
- Immutable image: `sha256:93dc39090e9fdf27cd1ba2bf9a93fcb68a68ef19fadfd45ac20cfc3cd1a3a2d5`.
- Fixed planner then executor; no memory, routing, learned rule or extra repair arm.
- Model `mistralai/ministral-3b-2512`, pinned provider `mistral`; temperature 0,
  recorded per-stage seeds derived from base 61, task, step and replicate.
- Two replicates per scenario; environment seed 100 for both. Provider seeds
  are recorded, not assumed to guarantee provider determinism.
- Maximum 15 steps; 384 planner and 768 executor output tokens per call;
  24,000-character public context. Each code/output history entry is capped at
  6,000/4,000 characters, respectively, with explicit truncation and omission
  metadata. Most recent history is retained. These caps are common-harness
  adaptations and possible performance limitations.
- Hard ledger cap USD 0.25 and 300 HTTP attempts, including retries and reserved
  ambiguous failures. At most 240 successful planner/executor calls if all eight
  episodes use the full horizon. Stop collection on a recorded provider failure.
- No workspace, key, evaluator or internet is available in the worker. Native
  guards and the shared action policy remain enabled. Public tool descriptions
  and errors are legitimate agent observations. Scoring occurs only after the
  episode and is never passed to the planner or executor.
- Evaluate both the live episode and independent final-prefix replay with the
  unchanged native evaluator. Eligibility requires equal verified tested state,
  public observations and native score, with expected recorded error positions.
- No interim prompt, model, selected-task or horizon changes. Investigate faults
  in a new recorded protocol instead of overwriting this run.

Train scenario groups are ordered by SHA256 of `[160906, scenario_id]`, excluding
the complete diagnostic/oracle group `07b42fd`; choose the lowest numbered task
variant in each selected group. No outcome-based selection. Allocations are:

| Partition | Task IDs | Use in this cycle |
|---|---|---|
| Build | 27e1026_1, b7a9ee9_1, 60d0b5b_1, aa8502b_1 | Eight no-memory episodes |
| Dev | 29caf6f_1, 82e2fac_1, 6ea6792_1, 76f2c72_1 | Reserved, not run |
| Audit | c901732_1, 229360a_1, e85d92a_1 | Reserved, not run |
| Evaluation | ccb4494_1, 2a163ab_1, 34d9492_1, 7d7fbf6_1 | Reserved, not run |

These are **train-derived development partitions**, not an official final-test
claim. Reserved task instructions and evaluator contents are not inspected.
The worker receives only the public bundle for the four build tasks; privileged
oracle outputs from cycle 5 cannot enter source selection, prompts or induction.

## Evidence and recovery policy

Save exact source/configuration, provider metadata, generation requests/raw
responses/usage, public handoffs, action inputs, typed frames, process output,
native scores, replay gates and eligibility reasons. Completed episodes and
model requests are reusable under identical provenance. Mid-episode crash
recovery is currently fail-closed: raw partial frames are preserved, but the CLI
refuses an implicit restart into an existing output directory. Audited recovery
must use separate records and prove the reconstructed boundary before another
paid continuation. This limitation is not described as full crash resumability.

Report every episode plus costs, parse fallbacks, local errors, native successes,
same-task mixed outcomes and replay failures. The cycle decision concerns source
and adapter sufficiency only. No learned superiority, causal improvement,
literature-baseline reproduction, transfer or submission-readiness claim is
permitted from this experiment alone.
