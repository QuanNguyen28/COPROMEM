# Evaluation 006 interruption and analysis exclusion

`v6_1_exploratory_diagnostic_evaluation_006_clean_restart` is immutable audit
evidence, classified **INFRASTRUCTURE-INTERRUPTED**.  The executor reached a
registered completion-token terminal response before submitting an AppWorld
program for `copromem_v6_1_dynamic / 4ec8de5_1 / trial 1 / seed 11001`.
The former evidence contract rejected its empty dispatcher journal even though
the executor request had settled and official scoring had completed.

Fourteen scored artifacts exist in the run, but none is eligible for a
comparative result or successor state transition.  The run's ledger reconciles
to 318 reservations, 318 settlements, and no unresolved reservations.  The
successor carries its settled exposure only as historical accounting.  It does
not copy artifacts, scores, histories, retrievals, or Dynamic states.

The repair adds a narrowly defined zero-action evidence branch.  It is valid
only for an executor settlement with a `length` finish reason at the frozen
2,048 completion-token ceiling, no tool call, no submitted action, an empty
dispatcher journal, and a durable official scorer record.  The canonical
binding includes trajectory identity, executor settlement and progress hashes,
model-output hash, termination, scorer evidence, manifest hash, and source
commit.  Empty journals remain invalid for ordinary completion, any submitted
action, missing scorer evidence, missing/ambiguous settlement, or malformed
telemetry.
