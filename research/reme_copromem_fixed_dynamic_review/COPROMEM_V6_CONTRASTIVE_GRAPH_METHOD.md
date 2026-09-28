# CoProMem v6: contrastive execution graphs

V6 supersedes v5.3 only as a new method branch.  It constructs deterministic,
value-redacted graphs from native dispatcher evidence, not agent source or a
guessed API chain.  Nodes contain public callable/type/effect metadata and
response status.  Edges represent order, public dependencies, and equality of
redacted producer/consumer hashes.

At a task boundary, all registered traces are batched.  At least two independent
officially successful, response-attested traces must support a common core;
failed traces penalize equally common exploration.  Read/discovery alternatives
are optional.  A public write terminal effect and typed public constraints are
required.  Candidates remain quarantined until pure validation succeeds.

Commit is transactional and idempotent.  Fixed state never changes during
evaluation; Dynamic updates only at a committed boundary after all task trials.
Retrieval first identifies semantic/effect-compatible schemas, then verifies
registry, public operations, types, terminal effect, and an executable supported
branch.  It returns empty guidance when no schema passes.  Guidance lists only
abstract public operation constraints and is reproducible byte-for-byte from
state, query, and provenance.

V6 does not retain concrete values, task IDs, responses, scorer details, hidden
state, expected answers, or provider text.  The official aggregate score is
only a success/failure label.
