# Successor efficacy-comparison protocol — design only

This is a proposal, not authorization to inspect tasks or make model calls.
It supersedes neither the immutable exposed-task plumbing record nor its
ledger.

## Custody and manifest

An independent custodian must create a fresh benchmark partition before any
agent receives task payloads.  The custodian publishes a signed manifest with
benchmark revision, split-construction code, task-ID hashes, creation time,
and a per-task exposure audit.  The experimental team receives task IDs and
payloads only after the manifest is frozen.  No `test_normal` payload may be
used.  If a defensible fresh AppWorld development partition cannot be made,
use a different benchmark with equivalent custody rather than relabel exposed
tasks as clean.

## Minimum design

* 12 disjoint acquisition scenarios, four shared trajectories each, frozen
  before evaluation.
* 48 disjoint evaluation scenarios spanning at least four predeclared task
  families; four independent execution seeds per arm.
* Arms: No Memory, ReMe fixed faithful adaptation, ReMe dynamic faithful
  adaptation, and CoProMem v2 (`include_contract_guidance=False`, defaults
  disabled only through the adapter).  ReMe remains labelled an adaptation
  unless direct upstream execution is separately verified.
* Same executor model/route, tool schemas, base prompt, task information,
  10-action cap, scorer, seed schedule, and isolated AppWorld state for every
  arm.  Memory text is the only allowed executor-input difference.
* Acquisition is shared and stored once.  Evaluation is fail-closed until the
  journal has complete native actions, official acquisition scores, frozen raw
  trace hashes, and non-generic, method-specific memory provenance.

## Estimands and analysis

Primary estimand: for each evaluation task, the difference between CoProMem's
mean official-success indicator across four seeds and No Memory's corresponding
mean.  The task—not the seed—is the independent unit.  Use a paired,
task-clustered bootstrap confidence interval and a paired randomization test.

Secondary, explicitly exploratory contrasts are CoProMem versus ReMe fixed and
dynamic; report task-level success, action count, valid-tool-call rate, latency,
and USD consumption.  Adjust the three planned contrasts with Holm correction.
Report failures and missing trajectories as failures, never silently exclude
them.

## Budget and decision rules

At a conservative ceiling of 6,144 input plus 512 output tokens per paid call
and USD 0.30 / 1M input plus USD 1.20 / 1M output, each call is bounded at
USD 0.0024576.  The maximum executor count is
`(12 × 4 + 48 × 4 × 4) × 10 = 8,160` calls.  Reserve an additional 25% for
registered ReMe/CoProMem lifecycle calls: 10,200 calls or **USD 25.06752**.
Set a hard all-inclusive cap of **USD 35**; do not use expected early stopping
to justify it.

GO only if custody, parity, artifact-completeness, and budget gates pass and
the primary paired estimate has a positive lower 95% bootstrap bound of at
least 0.05 success probability with adjusted `p < 0.05`.  KILL if a gate
fails, any arm receives non-equivalent task/tool access, the hard cap would be
exceeded, or the primary result fails either threshold.  A KILL result is not
evidence of method inferiority.
