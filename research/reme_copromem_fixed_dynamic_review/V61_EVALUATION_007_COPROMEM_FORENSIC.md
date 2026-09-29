# Evaluation 007 CoProMem integration invalidation

Evaluation 007 is immutable.  Its CoProMem Fixed/Dynamic comparison is
classified **INVALID-METHOD-INTEGRATION**.  The No Memory and official-upstream
ReMe arms remain exploratory diagnostic evidence only; they do not repair the
invalid CoProMem comparison.

The runner constructed a single query from initial-bank terminal effects and
passed it to all 24 CoProMem retrievals.  The retrieval callback did not use
the current public instruction or task metadata.  Consequently, six task IDs
produced one query hash, one guidance hash, and one selected schema ID.  The
same cross-domain learned guidance was injected into unrelated task domains.

The same runner also used a single evolving `state` variable for both arms.
After each Dynamic task update, subsequent Fixed retrievals read that Dynamic
post-state.  Thus Fixed was not semantically immutable and a Fixed-vs-Dynamic
claim is not interpretable.  The run contains four evolving pre-state hashes;
the per-task Fixed and Dynamic retrievals were drawn from the same state.

No raw task instruction, prompt, history, journal, credential, or guidance is
included here.  The v6.2 amendment replaces the bank-derived query with a
public task-conditioned query and maintains separate non-aliased Fixed and
Dynamic state owners.  Evaluation 007 artifacts, states, and scores remain
unchanged and are not reused by a future v6.2 evaluation.
