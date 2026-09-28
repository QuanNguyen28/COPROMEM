# Continuous CoProMem v5 run

CoProMem uses one `copromem_dynamic` arm. It starts from scored train trajectories and
continues learning after every evaluation task. The other arms are `no_memory`,
`official_upstream_reme_fixed`, and `official_upstream_reme_dynamic`. The manifest,
code, inputs, and dependencies are pinned for reproducibility; CoProMem memory is
not frozen.

## Inputs and preparation

Use a new run directory and `protocol: continuous_copromem_v5`. The manifest
lists the four arms, ordered evaluation task IDs, trial IDs and seeds, budget,
and `evaluation.descriptors`. Each descriptor maps a task ID to public,
pre-execution steps with `operation`, `input_slots`, and `output_slots`. It may
not contain an observed check, task-specific parameter value, or private scorer
data. A missing or incompatible descriptor produces exploration guidance. Preflight
writes `copromem/descriptor-audit.json` with initial compatibility for every task;
`evaluation.expected_initial_compatibility` may pin `compatible` or `unknown`
for selected tasks and fails preflight when an exact signature unexpectedly differs.
New tasks may legitimately start as `unknown` and learn online.

The acquisition export retains the scored public histories and unique episode
IDs. `prepare_v5` builds a mutable warm-start bank from these histories. For
each train task, it stores all episodes and promotes only the successful trial
with the best official score, then fewer actions and lower trial ID. Acquisition
exports do not carry per-trajectory cost; evaluation winner selection uses the
settled ledger cost before the action and trial ID tie-breaks.
The preparation audit checks episode coverage and state integrity; it does not
require replay or pre-admit memory by a held-out score.

Run preparation and manifest pinning using `prepare_v5` and `freeze_v5` in a
new directory. Existing v5 artifacts remain audit-only. Freezing the manifest
pins experiment inputs, not the evolving CoProMem bank.

## Online evaluation

For each task, all CoProMem trials receive the same bank snapshot and run in
separate processes. After every trial is scored, the controller records every
episode and promotes only the best structurally grounded successful candidate.
If all trials fail, it records failures without adding a positive procedure.
The resulting shared bank becomes visible at the next task boundary. Scored
artifacts, retrieval provenance, task snapshots, winner markers, and bank states
are durable and checked on resume; a completed task is not rerun or merged twice.

No validation replay runs before injection. Learned guidance is provisional.
Retrieval requires structural compatibility; unknown tasks explore. Matched
no-memory results provide a diagnostic harm signal, and harm on two distinct
tasks quarantines the affected schema. This rule is a guardrail, not a claim of
causal benefit. Reports show the pre-update score of each task and the online
memory timeline; validation performance is therefore an online learning curve,
not a frozen holdout estimate.
