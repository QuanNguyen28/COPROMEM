# Engineering 004 recovery integrity

Engineering 001 and 002 are immutable infrastructure failures. Engineering
003 is an immutable zero-dispatch preflight attempt. Engineering 004 may
continue the Engineering 002 allocation only by importing its single completed
No Memory trajectory as a content-addressed reference; it never copies or
rewrites predecessor evidence.

The v2 recovery envelope binds the source manifest and executable commit, a
manifest-derived legacy runtime identity, registry, artifact bytes, canonical
history, execution-evidence journal, scorer binding and scorer-journal bytes,
the complete source ledger, each ordered executor ledger record, the result
identity, and its exact schedule position. Engineering 002 predates a separate
runtime-identity record, so the envelope labels the reconstructed identity
honestly as `reasoningbank-manifest-bound-legacy-runtime-identity-v1`.

The completion marker embeds the exact frozen envelope. A valid marker is
read-only and idempotent. A partial, malformed, conflicting, or source-divergent
marker fails closed and is never overwritten. The successor ledger contains
one manifest-pinned historical carry record; predecessor ledger rows remain in
their original run and are not charged to a successor arm.

The execution reconciler requires completed work to be an exact prefix of the
frozen task-major schedule. Immediately after import, progress is 1/12 and the
next key is the second No Memory trial for task A. The ReasoningBank Dynamic
state remains the frozen empty initial bank until its first new trajectory is
scored and checkpointed.

This repair changes custody and recovery infrastructure only. It does not
change task allocation, prompts, model, temperatures, embedding transport,
ReasoningBank lifecycle, AppWorld execution, or official scoring.
