# Cycle 6 results: replayable failures, insufficient induction source

Completed 2026-09-16, approximately 01:54 UTC, on
`codex/copromem-research-loop` at unchanged HEAD
`18025102c010e85f26b0b3fb1144a1cb684b587e`. Decision: **REVISE** the common
source-collection workflow. Do not promote to a learned-memory comparison.

## Registered question and observed answer

The [preregistration](013_CYCLE06_SOURCE_PREREGISTRATION.md) asked whether a fixed
small planner/executor could supply replay-verifiable success/failure contrasts
on four outcome-independently selected AppWorld training scenarios. All eight
registered episodes completed their 15-step horizon. None passed the unchanged
native task evaluator. All eight final prefixes matched independent fresh-process
replay and received identical independent native evaluations.

The primary metric is therefore **0 of 4 scenarios with mixed successful/failed
eligible episodes**. This corpus cannot support the proposed same-task
outcome-contrast induction. No successful episode, candidate contract, admitted
bank, beneficial flip or learned-method result is fabricated from these failures.

| Training task | Replicate 0: native checks passed | Replicate 1: native checks passed | Local action errors, r0 / r1 | Replay |
|---|---:|---:|---:|---|
| 27e1026_1 | 1/2 | 1/2 | 10 / 15 | Both verified |
| b7a9ee9_1 | 1/4 | 1/4 | 15 / 15 | Both verified |
| 60d0b5b_1 | 0/7 | 0/7 | 15 / 13 | Both verified |
| aa8502b_1 | 1/4 | 1/4 | 15 / 15 | Both verified |

Check fractions are native diagnostic counts, **not fractional task success**.
The native Boolean task-success result is false for all rows. No completion flag
was raised. The independent sample contains only four scenario groups; no
population superiority or general impossibility claim is warranted.

## What failed in the source workflow

The separately implemented offline audit found:

- 120 total planning/execution steps; 113 recorded action errors.
- 114 executor outputs required the declared non-JSON fallback; only six parsed
  directly as the requested JSON code object. Two planner outputs used fallback.
- 91 programs failed Python AST parsing. A separate native compilation failure
  involved a top-level return; AST acceptance alone does not guarantee execution.
- 15 recorded rejections involved imports outside the shared action language.
  Additional native errors referenced nonexistent APIs or explicitly raised errors.
- Eleven programs had no AST call expression. This category overlaps with policy
  rejection and is not a task-success count. Strings/dictionaries may evaluate
  without performing any work, so a non-error tool result is not progress.
- Ten of 240 generations ended at the token limit; 230 reported normal stop.
  Truncation alone cannot explain the widespread formatting failures.

These are retrospective descriptive diagnostics, not replacements for the
registered primary metric. AST call sites do not prove actual invocation, and a
caught API exception may not have the worker's failure prefix. The native scorer
remains authoritative. Failures are not assigned wholesale to the planner.

## Strongest alternative explanation

The no-memory team was not yet a competent AppWorld baseline. A three-billion-
parameter backend was asked to produce escaped Python inside JSON while reasoning
through an unfamiliar tool interface, with limited onboarding and a short horizon.
The [public-interface audit](014_APPWORLD_PUBLIC_INTERFACE_AUDIT.md) identifies
concrete differences from the official minimal agent: richer onboarding, raw small
Python chunks, public supervisor information and explicit answer-completion
semantics. Cycle 6 did not provide equivalent onboarding.

Those weaknesses are plausible explanations, not experimentally isolated causes
of every failure. Both a model-capability limitation and poor interface design
remain live alternatives. A memory gain over this weak configuration would be
unconvincing if it merely teaches the agent how to use its public tools or format
code. Such knowledge belongs in the common baseline and static controls.

The registered protocol was not changed after observing early failures. Its full
sample and costs are retained. The train-derived dev/audit/evaluation scenarios
were reserved but not run or opened; the entire oracle scenario remains excluded.

## Costs and audit evidence

This cycle used 240 completed model generations and 240 HTTP attempts, with no
unsettled attempts or recorded provider failures. Reported usage was 808,122 prompt
tokens, 62,915 completion tokens and 871,037 total tokens. Settled provider cost
and charged/reserved ledger cost both equal **USD 0.06122978**, within the
registered USD 0.25 cap. Cached-input discounts mean raw tokens times the uncached
list price need not equal the provider bill. Archived usage and settlements agree.

Accumulated paid research cycles 1–3 and 6: 438 completed generations, 440 HTTP
attempts, USD 0.06638595 settled and USD 0.06744645 charged/reserved. The difference
is the two preserved ambiguous attempts in cycle 3. Offline diagnostics and local
native scoring add no model charge. Local compute was not monetized, so these are
external-model costs, not a full lifecycle-cost estimate.

Raw store: `artifacts/research/cycle06_appworld_source`.

- Collection report: `reports/27ca0abb8cdf7d67777fe9c295ce698ba8b2d55c61a55fe92def7ade522aba0b.json`.
- Complete offline audit: `source_audits/17a4d25a8fa1c551cd3c2dcc44b9e697db174b877818a15829b3ca7b4744f2ef.json`.
- Partial earlier audit is retained and explicitly labelled incomplete.
- Source snapshot contains all 33 selected implementation/environment files;
  none changed during the paid collection.
- All generation hashes, parsing decisions, public checkpoints, before/after
  frames and step counts reconcile. Paired native scores match, and evaluator
  execution did not alter persisted database files.
- All 118 local tests and Ruff checks pass. Tests deliberately corrupt fixture
  context, planner/code evidence and settlement data to check audit rejection.
- An actual-key scan of 1,528 selected source/test/research/evidence text files
  found zero matches. Original Markdown and DOCX research-document hashes are
  unchanged. No commit, push or deletion was performed. No Docker worker remains
  executing; stopped research containers and evidence are preserved.

## Decision and next experiment

**REVISE.** Retain the bounded replay/evaluator infrastructure, but reject the
sufficiency of this source protocol for outcome-contrast induction. Eight
replayable failures do not form successful/failed pairs and do not establish
useful stateful contract learning.

Next, implement a versioned common public-onboarding prompt for both roles and a
raw-Python executor response format. Keep the same model, provider, four build
scenarios, replicates, horizon and budget for an explicitly registered adapter
revision. This is a development comparison, not a memory treatment or new
generalization result. If basic tool use remains broken, test a stronger backend
under another preregistration instead of accumulating an artificial contract bank
from syntax errors. Stateful intervention, static/equal-compute comparisons,
independent admission and broader baselines remain downstream gates.

The overall research objective remains open. No causal learned advantage,
strongest validated replacement method or submission-readiness claim is supported.
