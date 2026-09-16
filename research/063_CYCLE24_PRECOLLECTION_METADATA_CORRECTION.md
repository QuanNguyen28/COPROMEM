# Cycle 24 pre-collection metadata correction

Recorded 2026-09-16 before any teacher request or native effect. The initial
preparation is preserved at `artifacts/research/cycle24_teacher_repair_source`,
protocol `5ecb83aceda8edb334bb30545f9246bb2271bfae963c68aed08418499b600c4e`.
It contains zero model calls, reservations and native executions.

The focused test found that `ast_identity` returns normalized AST text, not a
hash. The candidate field named `program_ast_digest` therefore needed
`digest(ast_identity(ast.parse(code)))`. The initial combined PowerShell command
continued into preparation despite the failing pytest exit status. Its saved
snapshot preserves the failing implementation and test; no outcome was collected
with it and it must not be used for paid collection.

Correct that field, advance the implementation namespace to v2 and use the new
write-once store `artifacts/research/cycle24_teacher_repair_source_v2`. Existing
prepared inputs, source snapshots and evidence are not overwritten or removed.
The current script supersedes that incomplete preparation; old source text remains
available in its snapshot rather than being falsely declared unchanged.

No task, source selection, teacher prompt, model/provider, token/cost cap,
proposal count, native-effect policy or scientific gate changes. Compare all four
input digests against the initial preparation. Run validation as a separate
successful command before invoking the new preparation/collection stages.
