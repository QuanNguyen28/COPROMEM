# Primary-source novelty audit — 16 September 2026

Status: targeted first-pass audit, not an exhaustive systematic review. Source-backed
method descriptions below are separated from our overlap interpretation. Numerical
claims from these papers have not been independently reproduced here. Dates and names
use the opened versions, not stale search snippets.

## Matrix

| Work / primary source | Memory unit and induction signal | Execution, scope and recovery | Setting | Closest overlap; remaining distinction to test |
|---|---|---|---|---|
| [ExpeL](https://arxiv.org/abs/2308.10144), [official code](https://github.com/LeapLabTHU/ExpeL) | Natural-language insights and recalled experiences from training trajectories | Text conditions future agent decisions; no deterministic handoff predicate established by the inspected sources | Interactive agent tasks | Experience-derived corrective knowledge is established. Our potential difference is explicit artifact checking and measured intervention admission. |
| [AWM](https://arxiv.org/abs/2409.07429), [official code](https://github.com/zorazrw/agent-workflow-memory) | Reusable workflows induced from experience | Retrieved routines guide generations; offline and online variants | Mind2Web, WebArena | Procedural reuse and selective retrieval are established. Handoff-contract validation needs a distinct mechanism and ablation. |
| [CRITIC](https://arxiv.org/abs/2305.11738), [official code](https://github.com/microsoft/ProphetNet/tree/master/CRITIC) | Current outputs plus external tool feedback | Tool-based critique followed by correction | QA, mathematical programs, toxicity reduction | Verification plus repair is established. Cross-episode learned trigger selection is the potential difference. |
| [ReasoningBank v1](https://arxiv.org/html/2509.25140v1) | Generalized textual strategies from self-judged successes and failures; MaTTS supplies multiple trajectories | Retrieval and consolidation feed agent context | Web browsing and software engineering | Success/failure learning and contrastive multi-rollout evidence are already present. A textual contrast-memory claim alone is insufficient. |
| [CONTRAMEM v1](https://arxiv.org/html/2608.22533v1) | Function/API Cards and Skill Cards distilled from same-task outcome differences across models | Retrieval includes task-start and pre-tool reminders; injected cards are soft guidance; localized curation | GAIA2/ARE and AppWorld | Extremely close to the original CoProMem premise. Candidate distinction: executable handoff predicates with independent downstream harm/benefit admission, rather than card guidance. This is an interpretation to test, not verified novelty. |
| [Skill-Pro v3](https://arxiv.org/html/2602.01869v3), [official code](https://github.com/Miracle1207/Skill-Pro) | Reusable skills with activation, execution and termination; semantic-gradient candidate generation | PPO-style gate evaluates historical advantage; score-based pool maintenance | In-domain, cross-task and cross-agent experiments | Executable skills, applicability and utility-based validation substantially overlap. A generic “executable memory plus admission” claim is inadequate. Search results still used the earlier ProcMEM title; v3 is Skill-Pro. |
| [AgentSpec](https://arxiv.org/abs/2503.18666), [official code](https://github.com/haoyuwang99/AgentSpec) | Rules in a DSL with triggers, predicates and enforcement; manual and LLM-generated rules studied | Runtime interception; actions include corrective invocation and reflection | Code, embodied agents and driving | Most runtime contract machinery has prior art. Remaining candidate distinction concerns matched outcome-based induction and its measured value, not the DSL alone. |
| [ProbGuard / earlier Pro2Guard](https://arxiv.org/abs/2508.00500) | Trace-derived probabilistic state model | Predictive runtime monitoring and intervention based on risk | Embodied and driving tasks | Learned monitors and proactive interventions overlap with alternative formulations. Latest abstract title differs from older search snippets; inspect version details before formal citation. |
| [ASI](https://arxiv.org/abs/2504.06821) | Program-based skills induced through interaction | Skill verification before use, composition and adaptation | WebArena and website transfer | Programmatic skill induction, validation and superiority over text skills are established. A contract must add more than executable skill representation. |
| [LEGOMem](https://arxiv.org/abs/2510.04851) | Modular procedural units from previous multi-agent trajectories | Memory allocated to orchestrator and task agents | OfficeBench workflows | Multi-agent procedural memory and placement are established. Ownership at a handoff alone may be a minor design variation. |
| [Automata from Agent Traces](https://arxiv.org/abs/2608.23670) | Compact FSM learned from trace corpora | Partial-trace failure prediction and runtime monitoring | Twelve public datasets per abstract | A finite-state-monitor pivot also has close prior art; do not assume representation change creates novelty. |
| [Daikon](https://plse.cs.washington.edu/daikon/) | Candidate program invariants inferred from observed executions | Dynamic invariant inference, rather than agent memory | Program analysis | Our bounded structural miner is an engineering instantiation of established invariant-mining ideas, not a standalone novelty claim. |

## Reviewer assessment

**Observation:** contrastive procedural memory, executable skills, verification, runtime
enforcement, utility gating and trace-derived monitors each have strong prior work.

**Interpretation:** the original broad CoProMem story faces high novelty risk. Renaming it
CoProCon and adding a static schema verifier does not resolve that risk.

**Candidate claim, currently unproven:** learn when a *specific public intermediate
artifact* needs intervention, choose a compact executable constraint from matched
outcome evidence, and admit it only after independent repair-benefit and benign-boundary
checks. Demonstrate that the learned applicability/constraint decisions improve quality
or cost relative to the same runtime with a strong human-authored verifier.

This claim survives as a **research hypothesis only**. In particular, Skill-Pro and
AgentSpec require deeper algorithm/code comparisons before claiming an unoccupied gap.
No “first” claim is justified by this audit.

## Evidence that would make the difference substantive

1. A static verifier and learned verifier share all execution machinery and input access.
2. Learned predicates or applicability rules differ for evidence-backed reasons; gains
   disappear in the relevant clause/scope ablation.
3. Savings cannot be explained by having an empty bank or declining all interventions.
4. Boundary checks measure harmful interventions on otherwise successful tasks.
5. Show at least two procedural domains before claiming general learning value.
6. If positioning around reduced specification effort, report expert-written clauses,
   authoring/editing time and repair iterations in a prospective study. Current automated
   clause counts alone do not measure human labor saved.

## Reproducibility cautions from this audit

- Official repositories and adapted local prompts are distinct evidence levels.
- CONTRAMEM's inspected HTML did not expose an official code URL; code availability is
  **unverified**, not asserted absent.
- ReasoningBank third-party repositories are not automatically official implementations.
- Current source access is not evidence that published scores reproduce on our harness.
- Broader benchmark pilots remain gated on adapter validation and mechanism evidence.

## Follow-up primary-code and recent-paper audit (16 September 2026)

This entry refines, rather than silently replaces, the first-pass wording above.

- **Skill-Pro representation clarification:** its published
  [Skill class](https://raw.githubusercontent.com/Miracle1207/Skill-Pro/main/data_structures.py)
  stores textual initiation/policy/termination fields for prompt formatting.
  It should not be described as a deterministic Python-predicate executor merely
  because the paper uses the options/skills formalism. Its
  [verification implementation](https://raw.githubusercontent.com/Miracle1207/Skill-Pro/main/Skills/skill_evolution.py)
  scores historical actions using old/new log probabilities and a clipped reward
  advantage surrogate; this inspected path is not a fresh paired environment
  rollout for each candidate. This strengthens the *mechanistic distinction* of
  direct intervention replay, but does not establish novelty or superiority.
- **ExpeL confirmation:** the pinned official
  [human critique template](https://github.com/LeapLabTHU/ExpeL/blob/e41ec9a24823e7b560c561ab191441b56d9bcefc/prompts/templates/human.py)
  explicitly takes a successful and failed trial of a task and updates reusable
  rules. Same-task contrast alone is therefore not a defensible novelty claim.
- **ProbGuard version:** the latest inspected
  [v4](https://arxiv.org/html/2508.00500v4) is titled ProbGuard. Use that version
  when comparing with the earlier Pro2Guard name.

| Additional primary work | Verified scope of inspected source | Consequence for our hypothesis |
|---|---|---|
| [ContractEval](https://arxiv.org/abs/2609.09458), submitted 8 September 2026 | Abstract describes query-active procedural obligations and matching against response/trace evidence; explicitly calibration-sensitive, not a compliance guarantee | Query-dependent obligations and graph conformance are not unoccupied concepts. Full-method comparison remains needed. |
| [SkillZip](https://arxiv.org/abs/2608.05604), August 2026 | Abstract describes contract-preserving procedural graph compression and execution-evidence updates | Compact contract-bearing procedural memory is not sufficient novelty. Its compression objective differs from learned repair selection. |
| [AgentSentry](https://arxiv.org/abs/2602.22724), February 2026 preprint | Controlled counterfactual re-execution at tool-return boundaries supports context purification against indirect prompt injection | Shared-boundary intervention diagnostics are prior art. A cross-episode learning contribution must be demonstrated separately. |
| [Knowledge-Based Zero-Replay Debugging](https://arxiv.org/abs/2606.14805), June 2026 preprint | Abstract proposes predicting high-effect events from trace features using replay-oracle labels | Learning where interventions matter also has close prior art. Distinguish online repair policy value from retrospective debugging/localization. |

These four additions are abstract-level screening, not a claim of exhaustive
algorithm inspection. No score from these papers was reproduced. A revised paper
claim must survive these comparisons; changing terminology is not a solution.

## Cycle-13 follow-up: traditional automated-repair overlap

The implementation now derives a producer block from an actual successful
program, transplants it into a failed program, tests it at frozen checkpoints and
attempts statement deletion. That progress adds a direct traditional-software-
repair comparison, not just agent-memory neighbors.

| Primary source | Verified overlap from inspected primary abstract/method summary | Remaining distinction, not yet a novelty claim |
|---|---|---|
| [Zeller and Hildebrandt, *Simplifying and Isolating Failure-Inducing Input* (2002)](https://www.st.cs.uni-saarland.de/papers/tse2002/) | Automated tests can reduce failure-inducing cases and isolate differences between passing/failing cases. The method explicitly distinguishes simplification and difference isolation. | Our evidence unit is an agent-generated final action at an environment/planner checkpoint. A new reusable scoped-monitor/repair contribution would still need to be demonstrated. |
| [Le Goues et al., *GenProg: A Generic Method for Automatic Software Repair* (2012), author-hosted paper](https://web.eecs.umich.edu/~weimerw/p/weimer-tse2012-genprog.pdf) | Statement-level program repair uses existing code and tests for desired behavior; structural differencing and delta debugging reduce candidate repairs. | Our proposal uses a successful same-task agent trajectory as donor and validates local effects in a stateful API environment. This alone does not establish a novel algorithm or transferable memory policy. |

These are focused primary abstract/method-summary checks, not full reproduction
or an exhaustive program-repair literature review. Our bounded greedy deletion
operator is **not** presented as `ddmin`, `dd`, genetic programming or GenProg.
We must not claim code transplantation, test-based minimization or contrastive
local repair as newly invented. Novelty, if any, must lie in a demonstrated
cross-episode scope/admission/recovery mechanism with attributable benefit,
or a carefully justified different contribution. Current cycle-13 evidence does
not establish that distinction. Static documented checks remain essential.

## Cycle-14 follow-up: omitted context-aware memory comparisons

This corrects a substantive omission in the earlier targeted search; it does not
retroactively make that search exhaustive. No new performance was reproduced.

| Primary work and inspected scope | Source-backed mechanism | Consequence for our research |
|---|---|---|
| [AutoGuide v2, sections 3.2--3.3 and algorithms 1--2](https://arxiv.org/html/2403.08978v2) | Contrasts same-task trajectories with different returns at their deviation point. An LLM summarizes the shared-prefix context and extracts a conditional textual guideline. Context matching organizes guidelines; context-dependent selection guides each test-time action. | Contrast, localized context, applicability and retrieval are already combined. AutoGuide must be a direct textual comparison; merely adding a scope field is not a contribution. The inspected procedure is prompt guidance, not our proposed independently effect-validated executable monitor. |
| [Experiential Reflective Learning (ERL) v2, section 2](https://arxiv.org/html/2603.24639v2) | Builds structured trigger/action heuristics from individual trajectories and outcomes; an LLM ranks heuristics for a new task before prompt injection. It does not require a matched success/failure pair for each heuristic. | A relevant alternative when matched-source collection is sparse. Contrast's acquisition cost must earn its keep against single-trajectory reflection, not just no memory. |

These inspected method sections strengthen the overlap concern, not a blanket
claim that every detail of our proposal exists already. Our *unproven* potential
distinction remains an executable applicability/verification/recovery object
with independent intervention-effect admission and measured harmful activation.
Cycle 13 establishes only one local program edit and has none of those validated
cross-task components. Neither switching to conditional textual memory nor
renaming a context into a contract resolves novelty. Official code availability
and exact baseline reproductions for these additions remain unverified here.

## Cycle-15 ReasoningBank source provenance correction

The [Google Research author page](https://research.google/blog/reasoningbank-enabling-agents-to-learn-from-experience/)
links to [the official source](https://github.com/google-research/reasoning-bank),
now pinned locally at `ed80611788292ea739f1effd31f16c53823b8a0d`.
[The focused static audit](029_REASONINGBANK_OFFICIAL_SOURCE_AUDIT.md) records
retrieval-cache mutation, cloud embedding paths, induction feedback modes and
vendored evaluator changes relevant to fair adaptation. This resolves official
repository provenance, not reproduction quality. No new performance result or
new novelty claim follows from cloning or parsing its source.

## Cycle-17 AgentSpec implementation clarification

The [pinned source and component fixture audit](040_AGENTSPEC_PINNED_PARSER_AND_ENFORCEMENT_AUDIT.md)
separates actual grammar, registry-backed predicates and runtime enforcement from
README-level features. Eighteen constructed probes repeat, but expose parsing,
trigger-input and dispatch limitations requiring honest adaptation. No full
policy or generated-rule comparison is established. These implementation findings
do not create a novelty gap: trigger/predicate/enforcement architecture remains
prior art, and a competent manually specified verifier/recovery control remains
mandatory. A weaker or broken baseline must not be used to manufacture learning value.

## Cycle-22 focused addition

[The Procedural Graphs primary-method correction](052_PROCEDURAL_GRAPHS_NOVELTY_UPDATE.md)
adds a close omitted comparison and records the inspected version, mechanism,
validation procedure and unverified code availability. Its consequence is to
reject contrast-plus-validation as a sufficient novelty claim. No prior entry
is deleted or silently upgraded into an exact reproduction. The remaining
learned-boundary hypothesis is still unproven in our repository.
