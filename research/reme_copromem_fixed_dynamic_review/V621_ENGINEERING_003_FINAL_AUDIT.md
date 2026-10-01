# v6.2.1 Engineering 003 terminal audit

This is a zero-provider audit of the completed, compatibility-conditioned engineering diagnostic. It is not an efficacy, superiority, transfer, or generalization result.

## Integrity outcome

The immutable run completed 30/30 registered trajectories. Its manifest SHA-256 is `4039749f27c88768f893f8fdd32a7836dfe6b547a85e478293eef209a58c5bd5`; its run-reconciled SHA-256 is `b89e09165aad35481c818af1df6e2d176e899ba99c2ff3aea9195df2c7f17f7f`. The terminal reconciliation is valid with zero failures, and the ledger has 632 reservations, 632 settlements, and zero unresolved entries.

The audit independently verified 30 unique registered identities, canonical history hashes, scorer bindings, execution-evidence bindings, executor settlements, retrieval records, fixed-bank checkpoints, ReMe Dynamic checkpoints, CoProMem Dynamic task-boundary checkpoints, and terminal/final-report manifest bindings. The executable commit is `5a9decb5c05060443bdce1d797578e1d078e4d16`; publication commit `1039815c3729b7f5a56b81341f25c3905a45dd70` only published the frozen run record.

One non-scientific reporting discrepancy remains: `live-summary.json` retains `state: reconciling` while `runner-status.json` is `completed`. Its counts, costs, final-report binding, and terminal reconciliation agree, so this stale label does not alter evidence or the engineering classification.

## CoProMem retrieval gates

All eight compatible-task CoProMem records selected a committed retrieval-visible schema, had non-empty guidance, injected that guidance into the model-visible prompt, and reproduced byte-for-byte offline. Both Dynamic trials for each task used the same frozen pre-task state.

All four negative-control CoProMem records had empty guidance and no selected schema. Their initial prompts were byte-identical to the paired No Memory prompts. The settled ledger assigns no ReMe lifecycle or embedding role to either CoProMem arm, so empty CoProMem retrieval did not fall back to ReMe. No post-allocation threshold change is present in the provenance.

The complete sanitized twelve-row record, including hashes, schema IDs, compatibility features, and state transitions, is in `v621-engineering-003-final-audit.json`.

## Dynamic lifecycle

For each task, both CoProMem Dynamic trials were durably scored before planning. The checkpoint chain preserves plan, validation, commit, post-state, and next-task authorization. The first task committed `schema_2e81e8a7c38832fc` and changed semantic state; the second produced a valid rejected marker and did not change semantic state; the negative-control task committed `schema_b16376ae57ac9c4a` after its retrievals and changed state only for subsequent tasks. A state change, a newly committed schema, a future retrieval change, and a score difference are distinct observations; none alone establishes a performance effect.

ReMe Fixed stayed at its frozen semantic identity. ReMe Dynamic has six ordered, reload-verified post-score checkpoint markers, one per online trajectory. Retrieval was non-empty for every ReMe record, with five retrieved memories each. Its prompt-memory overhead is consequently nonzero for every trial, whereas CoProMem is empty for the negative control and non-empty only where the frozen public compatibility rule admits a schema.

## Scores and interpretation

The observed raw means are: No Memory 0.809524; CoProMem Fixed 0.857143; CoProMem Dynamic 0.880952; upstream ReMe Fixed 0.928571; upstream ReMe Dynamic 0.642857. Against paired No Memory observations, CoProMem Dynamic has 2 wins / 3 ties / 1 loss and mean difference 0.071429; CoProMem Fixed 1 / 3 / 2 and 0.047619; ReMe Fixed 2 / 3 / 1 and 0.119048; ReMe Dynamic 1 / 2 / 3 and -0.166667.

These small, compatibility-conditioned, two-trial observations are suggestive diagnostic data only. Hash-bound retrieval, prompt injection, non-mutation, and checkpoint replay are deterministic integration evidence. Score differences may also reflect stochastic model generation and task difficulty. They do not identify a causal memory effect.

## Engineering decision

**ENGINEERING-VALIDATED.** CoProMem v6.2.1 task-conditioned retrieval is engineering-validated on the preregistered compatible/negative-control diagnostic.

## Evidence custody

The machine-readable audit and its checksum index contain only task IDs, arm/trial identities, scores, counts, schema IDs, public compatibility summaries, and hashes. They exclude task instructions, histories, raw journals, raw ledger records, memory text, scorer payloads, provider responses, and benchmark state.
