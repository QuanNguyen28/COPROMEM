# v6.2 protocol and method decisions

## ReMe Dynamic cadence

The pinned upstream lifecycle is sequential online adaptation.  The maintained
`dynamic_post_trial_update` invokes the upstream agent's `summary_memory`,
`add_memory`, metadata update, and pruning immediately after each durably
scored trajectory.  Therefore **official upstream ReMe Dynamic** remains
sequential.  Same-task trial 2 may observe the state produced after trial 1.

Future reports must call the two observations *ordered online trials*, not
independent seeded replicates.  Analyses must not use within-task independent
replicate assumptions for this arm.  Every trajectory must record the Dynamic
pre-state hash and update opportunity index.  CoProMem Dynamic instead has
task-batch granularity, so a comparison has different adaptation granularity.

Changing ReMe to same-pre-state task batches would be a new method named
**ReMe Dynamic Task-Batch Adaptation**, not official upstream ReMe Dynamic.  No
merge rule is implemented here; any such rule needs separate preregistration,
deterministic input/output semantics, and a new experiment.

## CoProMem learning policies

**CoProMem v5 winner-procedure memory** selects one successful episode under
its v5 winner policy.  **CoProMem v6/v6.2 contrastive common-core memory**
requires at least two response-attested successful traces and learns their
ordered common core.  Neither is a bug or a fallback for the other.  A future
ablation must preregister the policies as distinct arms and keep their states
separate.

## Proposed v6.3 structured guidance

v6.2 injects abstract public operation constraints only.  Proposed
**CoProMem v6.3 structured graph guidance** is a separate method, not a v6.2
repair.  It would deterministically render only committed, response-attested,
task-compatible public graph structure: ordered occurrences, public typed
input/output slots, supported dataflow/dependency edges, optional branches,
preconditions, checks, and a domain terminal effect.  It must never render
values, credentials, IDs, answers, responses, hidden state, or scorer data.
Unsupported or oversized guidance is empty.  Rendering must be byte-stable,
provenance-bound, offline reproducible, and prompt-bounded.

| Future ablation | Memory policy | Allowed claim |
|---|---|---|
| v5 winner | best successful v5 procedure | policy-specific exploratory result |
| v6.2 core | two-success semantic common core, abstract rendering | policy-specific exploratory result |
| v6.3 structured | v6.2 semantic core, graph rendering | rendering ablation only |

No arm may be selected after observing outcomes, and no state may mix these
policies.  None supports confirmatory efficacy, superiority, or broad
generalization without a separately powered and custody-valid study.

## Minimum zero-provider gates before a paid engineering run

1. Confirm ReMe Dynamic pre-state hash and ordered update index on every
   synthetic trajectory; prohibit independence statistics for this arm.
2. Verify v6.2 Fixed/Dynamic deep state isolation and semantic common-core
   transaction/restart prefix recovery.
3. Verify task-query compatibility, cross-domain empty fallback, and offline
   retrieval reproduction.
4. Verify a v6.3 renderer on direct, branch, optional, dataflow, overflow, and
   value-leakage fixtures before it can be evaluated.
5. Verify scorer-bound artifacts, ReMe Fixed pre/post canonical bank identity,
   runtime-content identity pins, and explicit stochastic-trial labels.

## Remaining blockers

No paid evaluation may be frozen until durable CoProMem Dynamic prefix
reconciliation, ReMe Fixed identity gating, runtime-content pinning, and the
trial/seed labeling decision are integrated and tested.  v6.3 structured
guidance additionally needs its own registry-safe renderer and ablation
protocol.
