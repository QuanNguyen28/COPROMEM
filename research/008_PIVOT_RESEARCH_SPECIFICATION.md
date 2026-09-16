# Research specification: effect-validated procedural contracts

Version: 16 September 2026, research-branch proposal following cycles 1–4.
Status: **a falsifiable pivot specification, not an implemented or validated new method**.
The implemented modules and observed results are distinguished throughout.

## 1. Problem and motivation

A fixed multi-agent workflow exchanges intermediate artifacts. Some artifacts look
incomplete but are sufficient for the consumer; others satisfy their schema while
causing semantic mistakes. Unnecessary correction can turn a successful trajectory
into a failure. The research problem is therefore not simply detecting an unusual
artifact. It is learning a compact, executable intervention rule whose application
has positive downstream value under a controlled budget.

The GSM8K evidence motivates this distinction. Cycle 1 found harmful static/sham
interventions and no beneficial ones. Cycles 2–3 found no discriminative structural
contract, even with more failed outcomes. Six Gemma success/failure pairs had the
same full planner artifact. Final-task failure cannot be treated as an infallible
label of a defective handoff. Unit ambiguity and output truncation add further
noise. These observations reject one representation/label configuration, not all
procedural learning.

## 2. Research question

Can a system learn **when and how to intervene at a public stateful handoff** from
paired continuation evidence, and transfer that rule to unseen tasks with a better
quality/cost tradeoff than a tuned static verifier using the same recovery path?

The team, role assignment, model and available tools remain fixed. This is distinct
from ARCO's adaptive within-episode orchestration question. Adding model routing or
adaptive teams to the main comparison would undermine attribution.

## 3. What a contract represents

A candidate contract is a tuple `(interface, applicability, predicates, owner,
recovery, provenance, admission_evidence)`. At a boundary it sees only information
that the acting system could actually observe: task instruction, public API
documentation, planned action/artifact, prior tool responses, and permitted state
observations. It must not read hidden evaluator tests, task solution code, future
observations, privileged database fields, or final-test outcomes.

The existing implementation supports structural predicates and simple public
categorical scope. A stateful extension may require cross-field relations, membership,
reference validity, ordering or state-change constraints. These are **proposed**
extensions. Their primitive semantics and any human-authored domain knowledge must
be reported; they do not become learned merely because an LLM chooses them.

The recovery route returns responsibility to the producing role. A generated
checker is not allowed to execute arbitrary Python, access the filesystem or add
tools. The static control and learned contract execute through the same interpreter
and recovery prompt constructor. Contract provenance must not itself change the
prompt seen by one arm.

## 4. Separate three labels

1. **Condition violation:** a predicate evaluates false on an observed artifact.
2. **Task failure:** the unchanged benchmark evaluator rejects a continuation.
3. **Intervention value:** a specified repair policy changes the continuation's
   quality and cost relative to no intervention at the same checkpoint.

These labels are not interchangeable. In particular, a violation may be harmless,
and a task failure may come from a later consumer error. A repair can fail to help
even when the violated condition is genuinely undesirable.

For a saved boundary state `s`, policy `a`, and matched replicate `r`, record
`Y(s, a, r)` and cost `C(s, a, r)`. The observed quality difference is
`D(s, a, r) = Y(s, a, r) - Y(s, no_intervention, r)`.
The target is expected downstream effect, not a claim that one paired random draw
reveals an immutable individual causal truth. Different prompts remain stochastic.

## 5. Candidate proposal versus candidate admission

Proposal can contrast same-task trajectories or use build-only public traces to
suggest a restricted rule. It should preserve raw proposals, parsed candidates,
rejections, support tasks and the path from source evidence to every decisive clause.
No minimum-support threshold may be weakened merely because the bank is empty.

Admission must use independent **intervention** evidence: replay the candidate,
no intervention, matched generic retry and static verification from the same state.
Measure beneficial flips, harmful flips, actual calls/tokens/USD and latency.
Minimize clauses on development data only, freeze before audit, and keep successful
counterexamples—including source successes that lack a matched failure.

The current four-dev/two-audit-task gate is an engineering smoke gate, not an
acceptable confirmatory safety guarantee. A main study must prospectively choose
its harm tolerance, minimum detectable benefit, confidence procedure, clustering
unit and sample size. Those choices require measured pilot variance; invented
sample sizes or post-hoc significance claims would not be defensible.

## 6. Fair intervention experiment

Use one immutable boundary checkpoint containing, or reconstructing exactly:

- public artifact and observation history;
- environment/database state;
- interpreter variables or a deterministic reconstruction procedure;
- simulated clock and random-state configuration;
- tool permissions and provider configuration.

A database snapshot alone must not be called a full checkpoint. The AppWorld
preflight specifically probes this distinction. Prefer isolated processes and
fresh arm-specific output directories so one arm cannot change global caches,
Python namespaces or the clock for another.

Harness-only restore is for **experimental matching**, not an extra capability
given to the proposed agent. Do not let one method undo actions while another
must live with them. Native environment actions and evaluators remain unchanged.

Identical effective provider requests may reuse a cached response as a common draw;
count this separately from physical collection calls. Distinct prompts require
their own recorded responses. Use multiple matched seeds, randomized arm order,
provider-route pinning and task/scenario-clustered uncertainty. Shared upstream
checkpoints do not eliminate all downstream stochasticity or service drift.

## 7. Required controls and attribution

| Comparison | What it can isolate | What it cannot establish alone |
|---|---|---|
| No memory vs induced contract | Total observed intervention effect | Learning value beyond a human-written rule |
| Success-only vs contrast proposal | Whether failed experience adds useful information | Executable enforcement value if prompts/calls differ |
| Textual version vs executable contract | Effect of enforcement rather than passive advice | Novelty of the memory content |
| Matched generic retry vs targeted recovery | Value of specific correction feedback | Learning value if trigger logic is still manual |
| Static vs induced, same runtime | Value of learned predicate/scope decisions | Reduced human labor unless labor is measured |
| Scope/clause deletions | Which learned components affect outcomes | Population guarantees from a tiny pilot |

Add a clearly marked retrospective best-of-controls upper bound only for diagnosis.
It may inspect gold outcomes after runs, but those selections must never be fed
to the evaluated policy or reported as a deployable method.

## 8. Benchmark sequence

Start with AppWorld **train/development** because task success is based on simulated
state changes and collateral effects, not only a free-form scalar answer. This is
a suitability hypothesis, not proof that it provides the needed transferable errors.
First validate one canonical adapter with reviewed actions. Then collect a small,
predeclared no-memory task stream to identify whether there are repeated public
handoff defects worth correcting. Include easy successes and benign boundary cases;
do not select only tasks where the proposed checker is expected to work.

Keep WorkArena++, SWE-bench and ALFWorld as benchmark-family candidates. Do not
install/run a large comparison grid until the first adapter and mechanism pass.
Scenario grouping, repeated task variants and permitted data usage must be checked
per benchmark; ID-disjointness alone may not imply template-disjointness.

## 9. Literature baseline fidelity

The current shortlist is ExpeL, AWM, ReasoningBank, CONTRAMEM, Skill-Pro and AgentSpec,
plus mandatory causal controls and optionally CRITIC. Native implementations,
paper-based implementations and common-harness adaptations must be labelled
separately. ExpeL/AWM checkouts now exist at their original pinned commits; only
bounded native probes have run. No published baseline result has been reproduced.

Skill-Pro's inspected gate scores historical actions with a log-probability
surrogate; a plain black-box text API may not supply the same information. Replacing
its gate with an LLM judge would be a material adaptation, not an exact reproduction.
Do not weaken it silently to fit the proposed method's API.

## 10. Novelty: what is already covered

Success/failure contrast is already present in ExpeL and newer memory systems.
Reusable procedural memory, validated skills and runtime rule enforcement have
close prior work. AgentSentry covers counterfactual tool-boundary diagnostics;
SkillZip and ContractEval cover contract-bearing procedural structure; learned
counterfactual-effect localization also exists. See the linked primary-source
matrix for verified facts and the limits of abstract-level screening.

Consequently, neither a new name nor combining familiar components establishes
novelty. The remaining candidate contribution is an empirically useful, compact
**effect-validated handoff contract** that transfers across tasks while explicitly
controlling harmful repair and beating the same runtime with a strong static rule.
This is a hypothesis. No priority/"first" claim or submission-readiness claim is justified.

## 11. Human specification effort is a different possible objective

Matching static performance with less expert authoring could be useful, but requires
prospective measurement of time, edited clauses, repair iterations and expertise.
Automatically counting fewer clauses is not a measurement of human labor saved.
Do not switch from accuracy to authoring effort after a failed test without a new
registered objective. This remains a secondary alternative, not a claimed benefit.

## 12. Promotion and kill criteria

Promote only when a nonempty frozen bank shows an attributable diagnostic benefit,
benign harm is acceptable under predeclared uncertainty, identical-checkpoint and
evaluator tests pass, and costs are reconciled. Independent confirmation must
survive the strongest static and retry controls before scaling.

Kill or reformulate if useful distinctions cannot be expressed from public state,
learned clauses merely restate the API schema, matched retry explains all gains,
repairs repeatedly harm benign tasks, or the nearest existing method already
implements the substantive mechanism. Preserve null results and useful infrastructure.

## 13. What is implemented now versus next

**Implemented:** immutable planner checkpoints; safe request cache; bounded provider
transport; six-arm schema diagnostic; generic structural mining; source/dev/audit
separation; greedy deletion; shared static/induced recovery; structural observability,
repair-effect and raw-artifact audits; primary-literature records; native dependency
preflight and supervised failure logging.

**Not yet established:** semantic/stateful contract induction, validated AppWorld
agent adapter, a learned intervention-effect estimator, calibrated harm control,
cross-domain transfer, full literature-baseline reproduction, or an accuracy,
efficiency or authoring-effort win.

The correct research status is **evidence-backed formulation pivot with preserved
experimental infrastructure**, not a finished AAMAS method.
