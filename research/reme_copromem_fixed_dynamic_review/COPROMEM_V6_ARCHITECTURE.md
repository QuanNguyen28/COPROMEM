# V6 architecture and evidence boundary

`native dispatcher → redacted evidence journal → canonical graph → task-batch
plan → validation → atomic state commit → two-stage retrieval → abstract
guidance`

The worker observes actual dispatcher entries, including calls in loops,
helpers, branches, and failures.  It never infers calls from source.  A node is
public callable/type/effect metadata plus redacted input/output equality hashes;
edges are order, declared dependencies, and equal producer/consumer hashes.
Raw values are discarded before graph persistence.

The graph builder is pure and content-addressed.  The planner sees aggregate
success/failure labels only.  A rejected plan returns the exact pre-state.
Fixed uses a read-only state; Dynamic may commit only after an entire task batch.
Each retrieval captures state/query/candidate/guidance hashes and can be replayed
without a provider.
