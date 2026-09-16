# Cycle 24: one-shot teacher repair sources for the four all-failure build tasks

Registered 2026-09-16 after the completed strict Cycle-22 decision and the
eleven-pair manual-selection ceiling. Cycle 23 remains paused and is not resumed.
This is a minimal source-acquisition experiment using the existing checkpoint
and native replay engine, not a learned-contract or teacher-superiority study.

## Why this experiment

The frozen 32-source build corpus has no eligible successful source for four
tasks: 27e1026 (oldest song across libraries), 3c13f5a (electricity-bill requests),
60d0b5b (refund an approved accidental payment request), and ce359b5 (remove old
songs). The other available mixed tasks only support the already inspected
pagination repairs. More mining of the same success/failure pairs cannot create
contrasts for these four all-failure tasks.

Hypothesis: one stronger-model, full-public-trace local repair proposal per task
can create at least one new exact-checkpoint beneficial contrast. Alternative
explanations include teacher prior knowledge, task-specific hindsight, direct
answer memorization, additional API calls and whole-workflow rewriting. A positive
source result does NOT establish learned memory, novelty or static-control value.

## Frozen selection and collection

Use source views from Cycle 17's frozen protocol digest
`a459726149f12360547116faf9e3098f0f5539dd077531abe41db5cf9331fe03`.
Select every task with no eligible success and its eligible fixed-team r0 source,
in ascending task-ID order. This gives exactly the four tasks above. No reserved
task, new split or source replacement after outcomes is allowed.

For each task, supply one teacher request containing the public task, all recorded
action indices/programs/outputs and public API documentation for observed apps
plus apps named by the task. Add supervisor/interface documentation. Never supply
hidden namespace values, evaluator tests, scorer subchecks or gold answers. The
binary source failure and later public history are explicit BUILD-only hindsight;
the result cannot be treated as an online repair that lacked that information.

Exact duplicate history entries may share one body with an explicit index list.
Programs are capped at 6,000 characters; truncated programs are ineligible patch
targets. Try output caps 12,000, 4,000, 1,000 then 0 characters until the complete
grouped history plus docs fits 180,000 UTF-8 bytes. Record every truncation and
never omit an action index. If no representation fits, record an unavailable
input instead of selecting a different task.

Model: `anthropic/claude-sonnet-4.6`, OpenRouter provider `anthropic` only, no
fallback, temperature 0, reasoning disabled, max output 2,048 tokens. The route
does not support seed; omit it from the transport. Any recorded logical seed is
only a cache identifier, NOT a determinism guarantee. Verify official endpoint
metadata and ceilings of USD 3/M input and USD 15/M output before collection.
Pricing source: https://openrouter.ai/anthropic/claude-sonnet-4.6.

Budget: **USD 3 maximum, four HTTP attempts maximum, one per task, no retries**.
Use the existing append-only budget ledger and generation recorder. Reserve a
UTF-8-byte token upper bound before each request. Retain ambiguous costs and never
restart an unresolved attempt. A transport failure stops further collection;
remaining planned tasks are recorded unattempted, not removed from denominators.

The teacher returns exactly one JSON object with action_index, code and diagnosis,
or null action_index/code to abstain. It may replace one eligible original action,
not append actions or modify the remainder. No syntax repair, second proposal,
best-of selection, hand-edit or native-score feedback is allowed. Validate the
original worker's program policy; do not execute generated code on the host.
Ask for a procedural repair that re-derives task-specific IDs/amounts via public
APIs rather than embedding values learned only later in the failed trace. This
request is not assumed to guarantee transferable code; inspect/disclose violations.

## Native effect stage

Run every valid proposal and a factual control from its exact selected original
checkpoint using the unchanged Cycle-17 `run_cell` engine and pinned image
`sha256:b5f9aaedde041e30fc4ff795ab46d47849cfc72701b9ffc8c8983fdefe36fcf6`.
Use the existing canonical public bundle and native scorer. Retain the entire
original future-action sequence, even if it overwrites the proposed repair.
Both live and fresh-prefix branches must agree; factual state/output/score must
match the original source. At most four valid proposals imply sixteen native
executions/scorers including factual live/replay controls. Invalid/abstained
proposals remain source failures in the complete four-task collection denominator.

Report source schema/policy failures, target indices, native effects, newly
introduced action errors, API-log deltas, elapsed times, requests, token usage,
settled/reserved USD and all unattempted slots. No positive-only filtering.

Primary source gate: at least one of four tasks obtains a native-successful,
completed, replay-eligible, no-new-error local effect. Zero on a complete valid
transport sample rejects this one-shot source protocol, not all teachers or all
learned contracts. A provider-incomplete sample is inconclusive, not a scientific
failure. Review the mechanism separately: new task IDs can still reflect ordinary
pagination or interface correction and do not establish a new learning nucleus.

KEEP only useful source evidence if this gate passes; otherwise REVISE/KILL this
source route as appropriate. No contract admission, held-out selection, baseline
superiority, scope transfer or validated pivot follows automatically. Future
methods/controls must share these teacher-generated build sources and acquisition
costs. No commit, push, deletion or change to earlier frozen experiments.
