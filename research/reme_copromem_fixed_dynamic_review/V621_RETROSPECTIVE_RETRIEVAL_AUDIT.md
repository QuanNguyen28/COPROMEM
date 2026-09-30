# v6.2.1 retrospective retrieval audit

Status: zero-provider diagnostic audit of immutable Evaluation 005.  It does
not alter a score, a trajectory, a bank, a ledger, or a scientific result.

## Historical defect

The legacy run had 120 CoProMem retrieval records: 92 `empty_public_query`, 28
`specific`, 1,916 candidate evaluations, zero selected schema IDs, and empty
guidance everywhere.  Its operation namespace and registry hash were already
consistent.  The failure was the predicate: it required a schema terminal and
all learned prerequisites to occur literally in a task instruction.  It also
mistook the complete generic public app catalogue for task relevance.

## Final v6.2.1 replay

The frozen v6.2.1 policy uses dot-delimited, underscore-preserving AppWorld
operation parsing; registry-declared operation aliases; a public HTTP action
class normalizer; exact terminal-effect compatibility; public typed constraints;
positive support; and directed public dependency checks.  It rejects
authentication, supervisor, API-document, quarantined, rejected, unsupported,
and reversed-dependency schemas.

Against each immutable Fixed state or exact Dynamic pre-task snapshot, the
final replay selected a schema at 20 of 120 points: 6/60 Fixed and 14/60
Dynamic.  It selected five schema IDs and produced deterministic, non-generic
guidance hashes.  Ten Fixed/Dynamic retrieval differences are bound to named
prior Dynamic commits in the machine-readable audit.  Every selected retrieval
reproduced byte-for-byte from its public query, frozen registry, and exact
pre-state; no selected schema was read from a later state.

An earlier intermediate replay reported 18 selected records and four
divergences.  During this audit, it exposed an underscore-namespace parser
error (`simple_note` was parsed as `simple`) and lacked public HTTP action
class normalization.  The final numbers above supersede that intermediate
diagnostic, which is not a frozen method result.

## Prompt validation

For each selected replay point, the source-agent `previous_memories` rendering
was reconstructed without executing a task.  The resulting model-visible
prompt hash differs from the paired No Memory prompt; it contains the selected
schema-derived guidance; its injected-memory hash matches the exact source
rendering; and repeated reconstruction is byte-identical.  For empty cases,
the reconstructed prompt is byte-identical to No Memory.  The maintained
callback disables the upstream fallback even when CoProMem guidance is empty.

## Semantic review

Each selected schema-task relationship records terminal compatibility, ordered
unique procedure operations, public dataflow/input-output checks, support
counts, failure warnings, nonsemantic-operation checks, and excluded-candidate
counts.  Terminal mismatch, same-app/different-effect candidates, incompatible
writes, reversed dependencies, failure-only records, infrastructure-only
records, and generic fallback all fail closed.  Repeated operations are retained
as audited multiplicity but are not rendered as an imperative loop without a
distinct response-attested dataflow reason.

The complete sanitized per-record evidence is
`v6_2_evaluation_005_copromem_v621_retrospective.json`.  It contains hashes,
public operation identifiers, schema identifiers, compact candidate-score
breakdowns, prompt identities, Dynamic-commit identities, and no task
instructions, histories, raw memory text, scorer state, journals, or values.

No score difference in Evaluation 005 is a CoProMem effect estimate.  This
audit establishes only that the repaired retrieval boundary is capable of
deterministic, provenance-bound, model-visible retrieval and empty-control
behavior offline.
