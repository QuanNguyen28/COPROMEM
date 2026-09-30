# v6.2 Evaluation 004 KeyError Forensic

## Scope and custody

This is a zero-provider, read-only forensic record for the immutable failed
run `v6_2_task_conditioned_evaluation_004_recovery`.  It does not change its
manifest, banks, journals, ledger, artifacts, or checkpoints.  It contains no
payload, action history, prompt, provider response, or secret.

## Failure

The runner failed in checkpoint writing, before semantic projection, planning,
validation, commit, post-state snapshot, or next-task authorization for
`042a9fc_1`:

```text
scripts/run_v61_exploratory_evaluation.py:264
copro_checkpoint.record(... scorer_evidence_hashes=[
    str(item['official_scorer_evidence']['sha256']) for item in copro
])
KeyError: 'official_scorer_evidence'
```

The failing dictionary was the durable, zero-action CoProMem Dynamic trial-1
artifact for that task.  Its available keys were the standard artifact identity,
history, score, execution-evidence binding, termination, and the explicitly
versioned `zero_action_evidence`; it intentionally had no ordinary
`official_scorer_evidence`.  Its trial-2 peer is the specified score-0.8,
30-action artifact with ordinary scorer evidence.

This is a **lifecycle implementation defect: a missing optional/versioned
field was incorrectly treated as required**, not malformed semantic input,
corrupted evidence, a method rejection, or a ledger/reporting issue.  The
invariant is now explicit:

- normal artifacts require `official_scorer_evidence.sha256`;
- only `actions == 0` artifacts bearing exactly
  `canonical-zero-action-evidence-v1` may instead contribute
  `zero_action_evidence.scorer_evidence_sha256`;
- every other shape raises `SemanticBatchEvidenceError` before a plan,
  validation, commit, or snapshot is written.

No scorer identity is fabricated or defaulted.

## Read-only reconciliation

- Valid unique scored artifacts: **20/300**: ten imported task-1 artifacts
  and ten newly executed task-2 artifacts.
- All 20 had matching canonical history hashes, evidence-journal hashes, and
  scorer-evidence hashes under their respective normal or canonical
  zero-action contract.  There was exactly one valid zero-action artifact.
- Ledger: **268 reservations, 268 settlements, zero unresolved**.  No
  provider replay occurred during this audit.
- CoProMem Dynamic task `024c982_2` is a complete, hash-valid committed
  prefix.  Its post-state hash is
  `1cff4e8192f853d9e835e7e6054346867a7b53584f0c9d61ee13b757885d0b75`.
- CoProMem Dynamic task `042a9fc_1` has only its frozen pre-state and durable
  retrievals.  It has no plan, validation, commit, post-state snapshot, or
  completion marker.  Its pre-state hash is that same task-1 post-state hash.
  Offline reconstruction after the typed normalization is deterministic and
  non-mutating: it produces a rejected marker, post-state equal to pre-state,
  and post-state hash
  `0aaf10c98e595c54deb97678a26554eb3efa22b0f3b691c62c654490a781ce9c`.
  This reconstruction must be persisted only in a separately versioned
  successor, never in the failed run.
- ReMe Dynamic has a complete ordered prefix of four reload-tested markers;
  its latest recorded post-update semantic hash is
  `5871658adb09f4c74fc730aaa8c5e5a1025d5bd51187393b3e0a1cf3f7401a2a`.
  ReMe Fixed has no write path and retains its immutable initial checkpoint.
- The runner and all owned ReMe services were stopped before the audit.

## Regression gate

The zero-provider gate now covers the canonical zero-action alternate scorer
identity, a production-runner shadow reaching the real
`trajectories_complete` boundary, three consecutive checkpointed task
boundaries, restart points, duplicate commits, mixed legacy/current semantic
representations, and fail-closed malformed evidence.  No successor may open a
new task payload until this gate and a content-addressed import/reconciliation
gate pass.

## Safe continuation boundary

The only possible continuation is a separately versioned successor that
imports the 20 hash-verified scored artifacts, restores the completed ReMe
prefix, copies the complete CoProMem task-1 transition, and records the
deterministic rejected task-2 transition from the exact durable inputs.  It
must next select the first uncompleted trajectory for the frozen task order;
it must never replay either scored task-2 trial.
