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
  retrievals.  It has no persisted plan, validation, commit, post-state
  snapshot, or completion marker.  The complete hash semantics are below.
  This reconstruction must be persisted only in a separately versioned
  successor, never in the failed run.

## Task `042a9fc_1` hash semantics

All values use `digest(value) = SHA-256(UTF-8 canonical JSON with
`ensure_ascii=False`, sorted keys, and `(',', ':')` separators).

| Object | Canonical object definition | Value |
| --- | --- | --- |
| Semantic pre-state | `{state_format, contrastive_v6_schemas}` | `1cff4e8192f853d9e835e7e6054346867a7b53584f0c9d61ee13b757885d0b75` |
| Semantic post-state | Reconstructed rejection return `post_state` | `1cff4e8192f853d9e835e7e6054346867a7b53584f0c9d61ee13b757885d0b75` |
| Pre-state snapshot container | `{state: semantic_pre_state, semantic_state_sha256: semantic_pre_state_sha256}` | `0aaf10c98e595c54deb97678a26554eb3efa22b0f3b691c62c654490a781ce9c` |
| Post-state snapshot container | Not persisted in the failed run; if a successor records the rejected post-state, its canonical snapshot is byte-identical to the pre-state container | `absent` (expected `0aaf10c98e595c54deb97678a26554eb3efa22b0f3b691c62c654490a781ce9c`) |
| Reconstructed rejected marker | `{state:"rejected", winner_schema_id:null, before_state_sha256, after_state_sha256, validation}` | `25eec1d0e44f93d3e0a42aaaa1af855c2a2ab1368b3457bebf7801af2697487c` |
| Plan semantic identity | `plan.plan_sha256` | `d3ad04d7de47a183f36b27cd6fb8600d2dc1c5e9ff51012a908a6f6bf8dfef7e` |
| Full plan container | `{min_successes, plan_sha256, plan_version, pre_state_sha256, schema, schema_id}` | `dc28ff9c3607f05d7ced59a000da39991e4dc4ee13f9545297257e5ac5e12421` |
| Validation | `{passed:false, plan_sha256, reason:"no_domain_operation", required_operation_count:0, terminal_role:"unknown"}` | `873fe663aa1fbd33abc315bd6b259073a1db4f3f8a4be54a980fbc757382edd7` |
| Full reconstructed audit container | `{state_format, semantic_policy_version, pre_state_*, semantic_graph_audits, plan, validation, marker, post_state_sha256}` | `213967a352eb3365fb94b90c39291c80d96926506d721aafad6fabfc2091487d` |
| Candidate schema | Audit-only candidate `schema_387a563b934a0f12`; it is not committed to `contrastive_v6_schemas` | `387a563b934a0f123327dbb69b29943ed6bc43869fe49ae324a68188e19c9252` |

The rejected marker itself is stored separately from a state snapshot.  It
does **not** enter the semantic state or snapshot container.  Therefore the
required invariant holds exactly:

```text
semantic_post_state_sha256 == semantic_pre_state_sha256
1cff4e8192f853d9e835e7e6054346867a7b53584f0c9d61ee13b757885d0b75
```

The semantic bank contains 12 schema IDs before and after reconstruction;
their ordered IDs and individual content hashes are identical.  Retrieval
operates only on that unchanged semantic bank.  The candidate is present only
inside the audit/plan object, has no committed schema entry, and therefore is
quarantined from retrieval-visible guidance.  The only permissible new durable
objects in a successor are the rejected-marker/checkpoint records; the failed
run itself remains unchanged.
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
