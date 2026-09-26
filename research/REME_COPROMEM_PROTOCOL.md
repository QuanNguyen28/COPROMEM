# ReMe versus CoProMem: preregistered DeepSeek adaptation

## Status and immutable provenance

This is a preflight protocol, written before any paid model call.  It is a
faithful adaptation, not a reproduction of the paper's Qwen3 experiments.

| Item | Frozen value |
| --- | --- |
| CoProMem source | `6eca54ca14a7935fcdcdc1a9a77319ed113a0679` |
| CoProMem ref at audit | `origin/experiment` and local `experiment` |
| Working branch | `codex/reme-copromem-comparison` |
| ReMe current main inspected | `8b5456641fc31e68c3a612753aa6d6692b83de2d` |
| ReMe paper-era branch inspected | `reme_v3` at `2f37a159b72a04ac1885a7db7f1a663a833e7791` |
| Paper | Cao et al., Findings ACL 2026, arXiv:2512.10696v2 |

Every result JSON, ledger, report table, and command emitted by a later run
MUST repeat the CoProMem SHA above and the selected dependency SHAs.

## Research question and preregistered claim rule

Does current CoProMem improve task-level success over no memory, A-Mem,
LangMem, ReMe-fixed, and ReMe-dynamic under equal task information, executor,
tools, iteration limit, trials, context budget, generation settings, and
official scoring?

The study must not call an outcome “CoProMem superiority” unless CoProMem
beats every listed arm under matched information and compute.  Any prior task
exposure, missing official scorer, unequal tool access, or protocol deviation
makes the relevant result exploratory and bars a generalization claim.

## Frozen arms

1. No Memory.
2. A-Mem: successful-trajectory-only addition, as specified by the ReMe paper.
3. LangMem: successful-trajectory-only addition, as specified by the paper.
4. ReMe fixed: paper-era ReMe distillation/retrieval with fixed memory after
   acquisition.
5. ReMe dynamic: the same ReMe implementation, with utility metadata update
   and deletion enabled.
6. Current CoProMem, unmodified except for a harness adapter.  It begins in
   its current no-contract-guidance default.  Contract guidance is not enabled
   in the primary comparison.

The harness adapter may only translate a common task/trajectory interface.  It
may not alter a method's memory content, retrieval policy, prompts, or scorer.
All method-specific differences are logged per task.  CoProMem ablations, if
implemented after the primary comparison is frozen, are success-only and
unpaired success/failure; neither is part of the primary six-arm ranking.

## Benchmarks, splits, and exposure screen

| Benchmark | Acquisition | Evaluation |
| --- | ---: | ---: |
| BFCL-V3 `base multi-turn` | deterministically sampled 50 of 200 | remaining 150 |
| AppWorld | 90 training tasks | 168 `test_normal` tasks |

Before a run, a split-generation script must write task IDs, source dataset
revision/checksum, split seed, ordering, and SHA-256 of each manifest under
`artifacts/research/reme_copromem_comparison/`.  It must reject overlap.
The audit must search CoProMem source, committed artifacts, ignored local
artifacts, and development reports for IDs/instructions from both evaluation
sets.  If this cannot establish clean holdout status, outputs are labelled
**exploratory / possible prior exposure**.

## Per-task procedure

For each of three independently frozen run seeds:

* Acquire up to eight trajectories per acquisition task at temperature 0.9.
  The executor has at most 30 iterations per trajectory and at most three
  failure reflections.  Save all successful, failed, timed-out, and malformed
  trajectories.
* Derive memories only from the acquisition partition.  ReMe receives top-K 5
  memories.  Dynamic ReMe uses deletion frequency/utility threshold `alpha=5`
  and `beta=0.5`; fixed ReMe does not mutate after acquisition.
* Evaluate every held-out task with four independent trials.  Retrieval happens
  once at task start for every retrieval arm.  No memory is written during
  evaluation in the primary analysis.
* Repeat the complete acquisition and evaluation process for three run seeds.

The executor and summarizer are both the selected DeepSeek route, with
non-thinking mode, no provider fallback, identical tool schema/access, equal
context cap, and identical sampling settings wherever the API permits.  The
exact endpoint, model ID, provider-reported revision, price snapshot, context
limit, temperature, top-p, max output, stop rules, and retry rules must be
written before the first call.  A provider refusal to offer a stable route is a
stop condition, not permission to substitute a model.

## Outcomes and analysis

For task *i*, Avg@4 is the mean of its four binary official scores; Pass@4 is
one when any trial succeeds.  Report benchmark means and standard deviations
across the three run seeds.  Tasks/scenarios, not trials or seeds, are the
independent units.

The primary comparison is CoProMem versus the strongest non-CoProMem arm,
chosen only after all raw outcomes are frozen.  Use paired task-level bootstrap
confidence intervals and a paired test appropriate to binary/continuous
task-level endpoints; apply Holm correction across primary pairwise arm
comparisons.  Also report paired wins/losses/ties; beneficial/harmful changes
versus No Memory; format, tool, environment, retrieval, memory, reasoning, and
scoring failures; calls, tokens, cost, wall time, tool operations, and memory
size.  Acquisition and evaluation cost remain separate.

## Gates

1. Install pinned dependencies and pass zero-cost unit/smoke tests.
2. Freeze manifests, scorer revisions, environment lock, provider route, and
   credential preflight.
3. Run only a development pilot in a separate, clearly labelled output tree.
4. Obtain explicit budget approval for the frozen full run.

No held-out outcome may tune a prompt, threshold, parser, split, or model.
