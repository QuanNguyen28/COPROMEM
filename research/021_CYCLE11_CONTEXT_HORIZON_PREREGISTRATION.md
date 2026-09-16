# Cycle 11: common context/horizon source diagnostic

Recorded 2026-09-16 before any cycle-11 paid generation. Prior goal turn: concrete
progress (completed cycle 9, cycle-10 runtime validation and ExpeL native component
checks), not an external blocker or a no-progress turn. Branch
`codex/copromem-research-loop`; HEAD remains
`18025102c010e85f26b0b3fb1144a1cb684b587e`. Preserve originals and all old evidence;
no commits/pushes/deletions.

## Question and falsifiable hypothesis

Can the same fixed no-memory planner/executor and coding backend supply usable
native outcome contrasts when the common workflow has more action steps and
retains more of its already-public observations?

Cycle 9 gave zero successes, seven horizon-limited episodes and frequent output
truncation. The hypothesis is that these shared resource/presentation constraints
contribute to inadequate source collection. The strongest competing explanations
are limited model/task competence, semantic goal drift, or the fixed role design.
Neither truncation nor the horizon was causally isolated in the prior data.

This is a **bundled baseline repair diagnostic**, not a causal estimate for any
one knob, not a learned-memory treatment, and not an equal-compute efficiency
comparison with cycle 9. More allowed calls and context explicitly cost more.
Improvement would support continuing with the better common workflow, not a claim
that CoProCon learned anything. Failure would justify deeper workflow/native-
baseline fidelity review rather than another unreported model switch.

Primary metric, unchanged: number of the four build scenarios containing both
native-success and native-failure replay-eligible episodes. Zero mixed scenarios
rejects this particular source protocol as sufficient for same-task outcome-
contrast induction. All-success would lack negative contrast; all-failure would
lack positive contrast. Do not hand-label local no-exception steps as successful
task trajectories to bypass this gate.

## Frozen configuration

Config: `research/configs/cycle11_appworld_source.json`.
Store: `artifacts/research/cycle11_appworld_source`.

Keep model `qwen/qwen3-coder`, provider `deepinfra/turbo`, temperature zero, the
recorded seed schedule 61 and environment seed 100. The provider route remains
exclusive, with fallback disabled and explicit parameter/price filtering. Fresh
metadata is stored before generation. Provider seed support is not determinism.

Keep the same v2 public role prompts, raw-Python executor, 384/768 planner/executor
output token caps, shared tools and native scorer. The tested cycle-10 image is
`sha256:b5f9aaedde041e30fc4ff795ab46d47849cfc72701b9ffc8c8983fdefe36fcf6`.
It preserves the declared native safeguards and extends the bounded capacity to
50 actions, with signed-infinity state observation and NaN still unsupported.
It is a new image, so cross-cycle checkpoint equivalence is not assumed.

The registered changes are:

- 50 action steps per episode, versus 15; no additional ad hoc retries beyond
  ordinary baseline interaction and the unchanged transport retry policy.
- A 64,000-character serialized public context, versus 24,000.
- Up to 16,000 characters per historical public output, versus 4,000. Historical
  programs retain the 6,000-character cap. Truncation/omission stays explicit.
- Public numeric metadata gives both roles total steps and remaining steps,
  including the current action. This comes from the declared budget, not private
  environment state. No new task hint, learned rule or evaluator feedback is added.

The new presentation is named `public-history-budget-v2`. Old configurations use
their exact prior contexts and retain identical saved audit IDs. Unit tests check
preserved longer public output, total-cap accounting, budget bounds, invalid
settings, hidden-state exclusion and audit rejection of a changed recorded budget.
Runtime capacity is checked before the first model call. A future memory/static/
retry comparison must share this entire presentation, horizon and tool interface.

## Data and budget

Use the same outcome-independent hash selection, first variant and two replicates:
`27e1026_1`, `b7a9ee9_1`, `60d0b5b_1`, `aa8502b_1`. These are build tasks, not a
fresh confirmatory test sample. Entire scenario `07b42fd` remains excluded after
oracle/diagnostic use. Dev/audit/evaluation partitions remain disjoint and their
instructions are unopened. No other task is substituted if one fails.

Budget: **USD 4.00** maximum for external-model usage/reserved ambiguous attempts,
within the user's USD 5 per-cycle authorization. Maximum 1,000 HTTP attempts and
at most 800 completed generations. Per-million provider price ceilings remain
USD 0.50 input and 2.00 output. Reservations occur before every attempt; unsettled
attempts retain their conservative bound. No extra funding is assumed if the
cap prevents completing the registered sample; report that sample as incomplete.

Full source/configuration snapshots are frozen before paid requests. Retain raw
provider responses, usage, public handoffs, action prefixes, live frames, errors,
native scores, independent replays and exclusions. Worker/provider crashes are
recorded, not silently restarted; incomplete live episodes require audited
recovery. Unsupported state excludes the episode from induction but not from the
overall outcome/cost denominator. No hidden evaluator label enters the prompts.

## Analysis and decision rule

Report the complete registered denominator, native successes, mixed-scenario
count, completion flags, horizon exhaustion, provider/action errors, parser
fallbacks, replay exclusions, calls/tokens/latency and settled/reserved USD. The
offline context audit additionally reports both historical 4,000-character and
declared 16,000-character output thresholds; those are descriptive diagnostics.
No post-hoc primary metric, significance, population generalization, learned-
contract efficacy or submission-readiness claim is permitted.

KEEP the revised common workflow only as source infrastructure if usable outcome
contrasts emerge and replay/usage audits pass. Any subsequent candidate still
needs genuine evidence-based proposal, independent effect validation, clause/
scope checks, static and equal-compute controls, and frozen disjoint admission.
If no usable contrasts emerge, REVISE the baseline/workflow or benchmark design;
do not scale to the six-baseline/four-family grid or call an empty bank successful.
