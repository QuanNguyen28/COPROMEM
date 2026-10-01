# ReasoningBank–AppWorld Engineering 006 Final Audit

## Scope and disposition

This is a zero-provider, read-only terminal audit of
`reasoningbank_appworld_engineering_006_clean_restart`. It did not start a
service, construct an AppWorld task, invoke a scorer, or make a model,
embedding, lifecycle, or provider request. The completed run directory remains
unchanged.

**Primary classification: `INVALID-METHOD-INTEGRATION`.**

The terminal execution evidence is internally valid, but the frozen
ReasoningBank retrieval provenance stores only a SHA-256 of each normalized
query embedding. It does not retain the embedding values or the cosine score
used for top-1 selection. Consequently, a separate zero-provider verifier can
reconstruct the injected bytes *after accepting the recorded selected
experience*, but cannot independently recompute or authenticate the top-1
selection and append-order tie-break. This is a retrieval-provenance method
limitation, not an AppWorld, scorer, provider, or checkpoint failure.

The sanitized machine-readable record is
`v621-reasoningbank-engineering-006-final-audit.json` (audit SHA-256
`d3823925807b3e11b7f41c4d972f3dcf8c07368daee52d1aa855f27833c49911`).

## Frozen identities and terminal integrity

| Item | Verified value |
| --- | --- |
| Executable commit | `a315f6ed371c15c25fc975fb3a970e563398a929` |
| Publication commit | `ed0e271a5ec9060e770ff1c1e0aecd6244643b73` |
| Manifest SHA-256 | `8f68bcead88dcfcad3af319de2580e0e10c8a25f578dff474a4c2aa2772393e6` |
| Terminal reconciliation SHA-256 | `3b9c44462e1afc5f593ffb26e685d9899a4b89718ef988b1a2b25f9432daf347` |
| Registered / valid artifacts | 12 / 12 |
| Dynamic checkpoint prefix | 6 / 6 sequential updates |
| Ledger | 192 reservations, 192 settlements, 0 unresolved |
| Historical / new / total exposure | USD 0.035249640 / 0.081421236 / 0.116670876 |

Every artifact has a unique frozen `(arm, task, trial, seed)` identity, a
canonical-history hash, a hash-bound journal and portable locator, a bound
runtime-identity file, and either ordinary or canonical zero-action scorer
evidence. The final report and `run_reconciled` marker both bind the frozen
manifest. This two-arm run did not register a ReasoningBank Fixed arm; Fixed
immutability is therefore not applicable rather than unverified.

## Dynamic lifecycle and retrieval observations

The six post-score Dynamic intents, snapshots, verifier dumps, settlement
intervals, and completion markers form a contiguous restart-safe prefix. Each
marker restores from its snapshot using the maintained checkpoint reconciler;
no incomplete intent, unresolved settlement, or duplicate update was found.

The first A retrieval was correctly empty from the empty initial bank. The
second A retrieval selected the first A experience. B trial 1 selected that
same prior A experience, so the predeclared A-to-B retrieval plumbing and
prompt injection are present. B trial 2 selected a prior B experience. Every
selected identity was present in its durable pre-state, every rendered guidance
hash was reconstructed from that state, and non-empty guidance was bound as
visible in the model-facing prompt.

The negative control retrieved non-empty memory on both trials. Its first trial
selected an A-family experience and its second trial selected an N-family
experience. This is the expected upstream top-1/no-abstention behavior, and is
recorded as a negative-transfer risk rather than as evidence of semantic
relevance. It was not forced empty or rerouted to another memory system.

## Why the reproduction gate fails

For five non-empty retrievals the persisted provenance contains:

- the normalized query embedding SHA-256;
- the pre-state SHA-256;
- the selected experience ID and hash; and
- the rendered guidance hashes.

It omits the normalized query-vector values and the selected cosine similarity
(as well as the ranked candidate score list).
Those values are necessary to recompute the top-1 ranking and deterministic
append-order tie-break without requesting a new embedding. A hash-only value
cannot supply them. The first empty retrieval is reproducible because its
pre-state has no candidate, but that does not repair the five non-empty
selection proofs.

No score, scorer evidence, future action, or post-outcome field is an input to
the persisted retrieval record. This rules out the inspected leakage paths; it
does not remedy the missing query-vector provenance.

## Scores are diagnostic only

Across the six paired observations, ReasoningBank Dynamic had one win, four
ties, and one loss against No Memory, with mean paired score difference
`-0.055556`. The observed aggregate ordering and action counts are descriptive
engineering observations only. They do not establish efficacy, superiority,
transfer, generalization, or a causal memory effect. Different stochastic
model trajectories and task difficulty remain plausible explanations for score
differences.

## Required next step

Do not use Engineering 006 for a reproducible memory-selection claim. Before
another paid comparison, create a separately versioned retrieval-provenance
contract that durably binds, per retrieval:

1. normalized query-embedding values and their SHA-256;
2. all top-k candidate IDs, vector hashes, and cosine similarities;
3. the selected ID, deterministic tie-break position, and rendered-guidance
   bytes/hash; and
4. the exact frozen pre-state and model-visible prompt-memory binding.

That amendment requires zero-provider tamper, restart, and byte-identical
selection-reproduction fixtures before any new engineering or confirmatory
run. It must not mutate or reinterpret Engineering 006.
