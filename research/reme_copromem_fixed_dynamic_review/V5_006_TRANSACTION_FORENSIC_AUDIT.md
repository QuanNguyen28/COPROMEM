# V5 006 task-boundary transaction forensic audit

## Scope and preservation

`v5_engineering_006_task_boundary` remains immutable. This audit used its
manifest and sanitized hashes only for committed diagnostics; it made no
provider, AppWorld, model, scorer, or embedding request.

The observed contradiction is confirmed: the A gate reported `full_success`
and an extracted procedure, but `fully_observed=false` and `passed=false`,
while the old live merge had already emitted a winner, provisional schema, and
changed bank state.

## Confirmed implementation bug

The old `complete_copro_task` sequence was not transactional. It constructed
`ScoredCandidate` values and called `apply_task_batch` on the live adapter
before the separate A acceptance gate in `task_boundary_v6` ran. That call
records episodes, creates schemas/procedures, selects a winner, promotes it,
and changes the exported state. The later gate could reject the result but
could not undo that mutation.

The A gate also contained a separate predicate defect: it required an event to
be `observed` **and** to have an empty `check`. The normalizer deliberately
uses `check="API response observed"` for a directly observed API result.
Consequently, the gate rejected its own positive evidence. The corrected
shared predicate treats `check` as evidence; it does not relax any public
observability requirement. The immutable 006 record remains rejected and is
not retrospectively relabeled.

The prior report-only offline reconstruction mismatch had a separate concrete
cause: a positional `RawAcquisitionTrajectory` construction placed normalized
events in the `handoffs` field. Its event field was empty. This was a forensic
reporting error, not a mutation of the 006 live state. The repaired boundary
uses named fields and one canonical commit/reconstruction function.

## Repaired behavior

`task_boundary.py` now provides a content-addressed, zero-provider sequence:

1. `plan_task_boundary_update` JSON-clones the supplied pre-state, sorts
   trials by `(task_id, seed, trajectory_index)`, and creates only candidate
   audit state on a private clone.
2. `validate_task_boundary_plan` evaluates success, observable evidence,
   strict structural signature, procedure eligibility, and the deterministic
   score/cost/action/index tie break.
3. `commit_task_boundary_plan` returns an unchanged pre-state for a rejected
   plan. For a valid plan it rebuilds the committed bank from the exact frozen
   trial records and verifies the planned winner.

Markers are now explicit `prepared`, `rejected`, or `committed` records. A
rejected marker has a null winner and an after-state hash equal to its pre-state
hash. Candidate audit state is not a retrieval bank and cannot supply guidance.

For 006, the *recorded* gate remains rejected. A current zero-provider
normalization of the durable histories shows observed, structurally valid
events; the previous false `fully_observed` classification comes from the
contradictory `not event.check` predicate. This audit does not rewrite the
run, create a retrospective committed winner, or use its state in any later
comparison.

The separate zero-provider reconstruction generated plan
`fc04d600…` from the immutable pre-state and the two artifact hashes. It
reproduced the stored post-state hash `ff0c8455…` and the stored deterministic
winner. This resolves the claimed reconstruction mismatch: the mismatch was
the report-only positional-field bug above. The repaired implementation still
enforces that no future failed plan can create that state.

## Predicate audit and method limitation

The current v5 `LearningCore.signature` predicate requires **every normalized
executor API operation** to be observed and to have usable inputs or outputs.
It therefore includes helper/auth/read operations when the parser recognizes
them; any unobserved loop/branch/nested operation makes the entire signature
ineligible. It does not use private scorer evidence or unavailable
postconditions.

That strict all-operations rule explains the 005 mixed/nested traces and is a
method-design limitation for ordinary AppWorld agent traces. It does **not**
explain 006: its recorded rejection was the contradictory gate predicate
above. The repair does not relax the strict v5 predicate.

See `v5-006-transaction-decision-trace.json` for hashes and the sanitized
decision trace.
