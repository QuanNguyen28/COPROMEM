# Failure-informed exploratory exact-ID-held-out pilot, v1

## Status and interpretation

This protocol is created after the immutable confirmatory acquisition stage
recorded **0/48 official full successes** and reached its preregistered NO-GO
decision.  It does not revise, reinterpret, or pass that gate.  The resulting
study is exploratory and failure-informed only: it cannot support
confirmatory efficacy, superiority, task-family, template-level, or
benchmark-wide generalization claims.  Its custody claim is exact-task-ID
holdout only.

The versioned manifest is generated before any evaluation task is started at
`artifacts/research/reme_copromem_comparison/openrouter_failure_informed_exploratory_pilot/manifest/failure_informed_exploratory_v1.json`.
It contains content hashes for all 48 source score artifacts and trace
references, the source terminal record, 30 frozen evaluation IDs, two seeds,
route settings, parity settings, lifecycle settings, and analysis plan.

## Source pool and lifecycle rules

All 48 frozen acquisition trajectories are used exactly once as lifecycle
input, including every failure.  No trajectory is replayed or filtered.

- ReMe fixed faithful adaptation receives only acquired successful procedural
  memories.  With this source pool it legitimately emits an empty memory.
- ReMe dynamic faithful adaptation starts from that same empty acquired pool;
  it maintains independent seed streams and applies its registered
  utility/frequency failure-aware post-evaluation update.  It does not invent
  an acquisition procedure from a failure.
- CoProMem v2 has its defaults disabled, records every failure as an episodic
  observation, and retains its native decomposition/admission/consolidation
  logic.  Empty retrieval is permitted.

No generic advice, authored repair, or synthetic success may be supplied as
executor memory.  Every lifecycle output and per-trial memory input is
write-once and provenance-bound to the source-pool hash.

## Evaluation and parity

Thirty frozen exact-ID-held-out tasks × two frozen seeds × four arms × at most
30 actions yields 7,200 evaluation executor calls.  Arms are No Memory, ReMe
fixed faithful adaptation, ReMe dynamic faithful adaptation, and CoProMem v2.
The sole permitted executor-input difference is the recorded memory suffix.

All calls use the locked OpenRouter route: `deepseek/deepseek-v4.1-flash`,
DeepSeek only, fallback disabled, non-thinking, non-streaming, one declared
native function tool with voluntary selection, and a 1,024 completion-token
ceiling.  The response gate requires exactly one valid call to the declared
function.  One declared tool plus the exactly-one-call gate disables parallel
tool execution.

## Budget and stopping

Every historical local reservation is carried forward: 1,101 records and USD
0.77752978 charged-or-retained exposure.  New registered dispatch capacity is
7,200 executor calls plus 320 CoProMem decomposition calls, all at USD
0.003072: USD 23.10144000.  ReMe adaptation lifecycle calls are deterministic
local operations (zero paid calls).  The non-dispatchable 15% contingency is
USD 3.46521600.  The complete all-inclusive bound is **USD 27.34418578**,
below the USD 35 hard cap.

The ledger separately enforces the 7,520 new-attempt limit and cumulative
USD 23.10144000 reservation envelope, so settlement savings cannot fund an
extra unregistered request.  It stops before a route/authentication failure,
native runtime/scorer failure, parity failure, 10 GB C-drive-floor breach, or
budget breach.

## Analysis

The analysis unit is a matched task × seed outcome.  It will report per-arm
official success rates, paired arm-minus-No-Memory differences, and
task-clustered bootstrap uncertainty intervals.  Any observed difference is
descriptive and exploratory, not confirmatory.
