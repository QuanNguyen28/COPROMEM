# Evaluation 006 orchestration shadow gate

Before evaluation 006 allocation is frozen, the maintained
`run_v61_exploratory_evaluation.run` control flow is exercised with two local
synthetic tasks, two trials, and all five registered arms (20 artifacts).
Only external executor, provider/service HTTP, and scorer boundaries are
replaced.  The production ledger, evidence contract, live summary, artifact
layout, ReMe Dynamic checkpoint manager, status finalization, task ordering,
and CoProMem task-batch boundary remain in use.

The shadow asserts a durable summary after each artifact, a 20/20 terminal
summary, per-arm accounting, no duplicate artifacts, and a failed status with
lock cleanup for injected interruption points.  Its regression sequence
reproduces the relevant evaluation-005 ordering: No Memory then ReMe Fixed
produce separate durable summaries before an interruption at the next work
unit.

It is zero-provider, zero-AppWorld, and zero-scorer validation.  Existing
dedicated lifecycle and checkpoint suites cover the detailed intent, snapshot,
verifier, marker, and ambiguous-restart states that the orchestration invokes.
