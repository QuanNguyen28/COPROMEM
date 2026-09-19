# COPROMEM 2.0

## Structural Schema Memory for Safe Procedural Reuse in Agent Workflows

**Document status:** prospective research specification for an AAMAS-oriented
method paper.  This is not a report of a completed experiment, a claim of
novelty, or authorization to resume the killed AppWorld study.

**Scope boundary:** COPROMEM 2.0 is a new formulation motivated by the
CoProMem/CoProCon 1.x record.  The old code, replay harness, source records,
and negative findings are retained as engineering and diagnostic evidence; they
are not evidence that the new method works.  In particular, no current result
shows a learned contract bank, cross-scenario transfer, or superiority over a
strong static/manual control.

---

## Abstract

Agent memory systems often retrieve a past trajectory, workflow, or textual
lesson because it is semantically similar to the current task.  This can be
harmful when similar language hides a different dependency structure: a
procedure that was correct for one workflow is reused in a context where its
preconditions do not hold.  COPROMEM 2.0 studies this *semantic--structural
conflict*.

The proposed method stores a **typed decomposition schema**: an observed
dependency graph over workflow roles/subtasks, typed handoff obligations, and
an explicit applicability boundary.  At test time, it combines semantic
retrieval with graph alignment.  A high semantic score is insufficient for
reuse: when a candidate schema is structurally incompatible, the system vetoes
reuse and records a separation example rather than injecting the prior
procedure.  The central empirical question is therefore narrow and falsifiable:
under matched information, model, and inference budget, does graph-conditioned
retrieval reduce negative transfer on tasks with high semantic similarity but
low structural similarity?

This document specifies the method, its non-claims, a controlled 2x2
evaluation, the required baselines, and decision gates.  A multi-agent claim is
permitted only if the final evaluation contains genuine role-to-role handoffs;
otherwise the work must be positioned as structural memory for single-agent
workflows.

---

## 1. Why a new formulation is needed

### 1.1 What the previous program established

The CoProMem/CoProCon 1.x record established useful, bounded engineering
capabilities:

- isolated execution, saved-prefix replay, and unchanged native scoring on
  supported AppWorld states;
- content-addressed protocols, raw-response capture, and cost accounting;
- static/public-binding inspection; and
- local repair opportunities in a small number of inspected continuations.

It also established constraints that the new work must respect:

- domain-authored synthetic contracts are not evidence of automatic induction;
- GSM8K comparisons were unstable and confounded by independently generated
  upstream plans;
- the old AppWorld allocation has no affirmatively certified untouched test
  capacity and is **not** a valid confirmatory test set;
- the old code-only predicate representation could not distinguish contextual
  outcomes;
- a binding-aware static checker solved the measured missing-name class; and
- on eleven fixed original/edit pairs, a post-hoc manual risk policy attained
  the available quality oracle (8/11).  No new selector can beat that oracle on
  those same candidates.

The appropriate conclusion is not that memory is impossible.  It is that a new
claim needs a new mechanism, a clean evaluation population, and controls that
rule out static analysis, ordinary debugging, extra compute, and hindsight.

### 1.2 The gap addressed here

Existing work already covers experience-derived insights, context-aware
guidelines, procedural/workflow memory, dynamic memory refinement, and
multi-agent memory placement.  COPROMEM 2.0 must not claim that any of these
ideas is new.  Its candidate contribution is more specific:

> **When semantic similarity and observed workflow structure disagree, use
> typed structural alignment to veto procedural reuse, and retain the conflict
> as evidence for future schema separation.**

The paper succeeds only if this mechanism produces a measurable reduction in
negative transfer that is not reproduced by semantic trajectory retrieval,
textual procedural memory, or a semantic retrieval system with equal compute.

### 1.3 Research questions

**RQ1 — Structural transfer.** Does a reusable typed decomposition schema help
when task semantics change but the dependency structure is preserved?

**RQ2 — Structural veto.** Does graph-conditioned retrieval reduce harmful
reuse when task semantics are similar but the dependency structure differs?

**RQ3 — Optional supporting diagnosis.** Do typed handoff obligations make
errors more localizable than generic reflection, without claiming causal blame?

RQ1 and RQ2 are the paper's core.  Continual consolidation, replay priority,
anti-lock-in exploration, and recovery are secondary extensions.  They should
not enter a first experiment unless RQ1/RQ2 clear their gates.

---

## 2. Problem setting and terminology

### 2.1 Workflow episodes

An episode is an execution of a task (x) by a workflow with roles or
subtasks (V = \{v_1, \ldots, v_n\}\).  The observed trace is

\[
\tau = (o_0, a_1, o_1, \ldots, a_T, o_T),
\]

where observations and actions are restricted to information available to all
compared methods.  A task-level evaluator returns (Y(\tau) \in \{0,1\}),
and may additionally expose public intermediate artifacts.

An *independent unit* is a task scenario/workflow template, not a seed,
continuation, checkpoint, action boundary, or replay branch.

### 2.2 Observed decomposition schema

A schema is a typed, directed acyclic graph

\[
S = (V, E, \ell_V, \ell_E, C, A),
\]

where:

- (V) are abstract role/subtask nodes;
- (E) are observed dependency or handoff edges;
- \(\ell_V\) assigns a node type, such as retrieve, filter, validate, rank,
  commit, or delegate;
- \(\ell_E\) assigns a handoff type, such as candidate set, constraint set,
  selected entity, or validated action;
- (C) is a set of typed handoff obligations; and
- (A) is an applicability boundary containing positive and separation
  evidence.

This is an **observed dependency schema**, not a causal graph.  The method may
claim causal effects only in an experiment that randomizes an intervention and
measures an outcome under a stated causal estimand.

### 2.3 Handoff obligations

For edge (e=(u,v)), a handoff obligation is

\[
c_e = (\text{input type},\; \text{predicate},\; \text{evidence extractor},\; \text{action}),
\]

with a deterministic or auditable predicate over public artifacts.  For
example, a ranking subtask may require a nonempty candidate set whose elements
contain all hard-constraint fields before it can commit a choice.

An obligation is not automatically a learned causal rule, a responsibility
assignment, or a repair policy.  It is an executable/inspectable condition at
a workflow boundary.

### 2.4 Similarity regimes

Let (s(x,S)\) be semantic compatibility between a task and a stored schema,
and (g(\hat S_x,S)\) be typed graph alignment between an extracted task schema
\(\hat S_x\) and the stored schema.  The paper studies four predeclared regimes:

| Semantic compatibility | Structural alignment | Intended policy |
|---|---|---|
| High | High | Reuse candidate schema |
| Low | High | Transfer schema despite wording shift |
| High | Low | Veto reuse and record separation evidence |
| Low | Low | Do not reuse |

The key RQ2 regime is **high semantic compatibility + low structural
alignment**.  It is not enough to label examples this way after observing
method outcomes; labels must come from a benchmark generator or blinded,
pre-specified annotation protocol.

---

## 3. Method: Structural Agreement and Vetoed Retrieval

### 3.1 Design principle

COPROMEM 2.0 does not replace an agent's planner.  It decides whether a stored
procedure is eligible to condition that planner.  Its central safety property is
modest: a semantically attractive memory should not be injected merely because
it is linguistically similar.

### 3.2 Schema extraction

Given a task specification, public tool/API metadata, and an optional public
plan prefix, an extractor produces:

1. node types;
2. candidate typed dependencies;
3. expected handoff artifact types; and
4. uncertainty for each node/edge.

The extractor can be implemented by a constrained LLM decoder, a parser over a
typed planning language, or a hybrid.  The chosen implementation must be fixed
before held-out evaluation.  It must emit a machine-readable schema and a
validation trace, rather than only natural-language rationale.

Extraction is evaluated separately from task success on a benchmark with known
structural labels.  If it cannot recover usable typed structure on development
data, the project stops before end-to-end agent experiments.

### 3.3 Structural alignment

For a query schema \(\hat S_x\) and stored schema (S_i), compute a typed graph
alignment score:

\[
G_i = \operatorname{Align}(\hat S_x, S_i; \ell_V, \ell_E, C).
\]

`Align` must be predeclared.  A practical initial option is normalized typed
graph-edit similarity with explicit penalties for missing prerequisite edges,
incompatible handoff types, and violated required obligations.  The paper must
report its components, not only a single opaque score.

Semantic compatibility is calculated by the same embedding/retriever used by
all semantic-memory baselines.  This prevents COPROMEM from receiving a
stronger semantic representation by construction.

### 3.4 Retrieval policy

Each memory candidate receives a semantic score (R_i), a structural score
(G_i), and an extraction confidence (Q_i).  The initial policy is:

\[
\operatorname{reuse}(S_i \mid x) =
\mathbb{1}[R_i \geq \tau_R \land G_i \geq \tau_G \land Q_i \geq \tau_Q].
\]

If \(R_i \geq \tau_R\) but \(G_i < \tau_G\), COPROMEM issues a **structural
veto**.  It does not inject (S_i) as procedural guidance.  The run either
uses no memory or a separately selected structurally compatible candidate; it
must not silently receive extra planning calls.

Thresholds are calibrated only on a development split.  The calibration
procedure, candidate count, tie-breaking rule, and abstention behavior are
identical for all reported test runs.

### 3.5 Separation evidence and bank update

A separation record is

\[
z = (x, S_i, \hat S_x, R_i, G_i, \text{veto reason}, Y),
\]

stored in a fast evidence buffer.  A record is not a new schema by itself.
Promotion/branching requires predeclared repeated evidence of a distinct typed
structure on independent development tasks.  This guards against creating a
new schema for every noisy episode.

The first paper should use a conservative, transparent update rule rather than
claim a neuro-inspired continual-learning algorithm.  A fast/slow memory or
prioritized replay extension is allowed only after a controlled stability study
shows a benefit over immediate updates, random replay, and frequency replay.

### 3.6 Handoff contracts as a supporting mechanism

When a reused schema has an obligation (c_e), its verifier is run only on the
public artifact designated by that edge.  On failure, the system records a
handoff violation and takes the predeclared local action (for example: request
the immediately preceding subtask to produce the missing typed artifact).

This supports a *local verification* claim.  It does not support claims that
the upstream role is morally responsible, that the violation is the unique root
cause, or that recovery is optimal.

---

## 4. Hypotheses and falsifiers

| ID | Hypothesis | Confirmatory evidence | Falsifier |
|---|---|---|---|
| H1 | Structural schemas support transfer across wording shifts. | Full method exceeds no-memory and raw semantic RAG in the low-semantic/high-structural test regime. | No improvement, or equivalent improvement from semantic RAG under matched budget. |
| H2 | Structural veto reduces harmful procedural reuse. | Negative-transfer rate is lower than raw semantic RAG and the no-veto ablation in the high-semantic/low-structural regime. | No semantic-RAG negative-transfer headroom, or veto fails to reduce it. |
| H3 | The effect is structural rather than a larger prompt or more inference. | Full method beats semantic-only/no-veto arms while retrieved tokens, candidates, planner calls, model, and tools are matched. | Effect disappears under budget matching. |
| H4 | Typed handoff checks improve local handling of injected boundary faults. | Higher obligation-violation precision and recovery/locality than a generic critic on a separately held-out injection set. | Checks are inaccurate, prompt-only critic matches them, or benefit is only an artifact of injected labels. |

The paper must not make claims about general continual learning, causal
responsibility, general safety, or multi-agent superiority unless separately
tested with their own matched controls.

---

## 5. Evaluation design

### 5.1 Phase 0: feasibility and headroom

Before building a full agent adapter, construct a development-only controlled
suite with a fixed task grammar and independently randomized surface forms.
Each item has a hidden typed workflow schema.  The generator creates the 2x2
semantic/structural design without using method outcomes.

Phase 0 asks two questions:

1. Does semantic trajectory retrieval cause measurable negative transfer on
   high-semantic/low-structural cases?
2. Can the schema extractor and typed alignment detect the conflict better than
   semantic similarity alone?

If semantic RAG has negligible harmful reuse, there is no headroom for a
structural-veto paper.  If the extractor cannot separate the regimes on a
development set, end-to-end gains cannot validate the intended mechanism.

### 5.2 Phase 1: controlled confirmatory suite

The main mechanism evaluation uses a frozen **SchemaConflictBench** test split:

- the task grammar, graph labels, surface paraphrase generator, splits, and
  scoring are versioned before model runs;
- train, development, and test templates are disjoint;
- no test task text, graph, or outcome is opened while developing extraction,
  thresholds, or prompts;
- all methods receive identical public task/tool information, model, maximum
  calls, token budget, candidate count, and execution budget; and
- trials are clustered by template family for confidence intervals.

The custom suite is a mechanism test, not a replacement for a realistic
benchmark.  Its release must include the generator, hidden-seed procedure,
schema annotation rules, and every task instance used in reporting.

### 5.3 Phase 2: one external benchmark

Choose **one** external setting after Phase 1, not five simultaneously.

- If the paper claims multi-agent handoffs, use an environment with actual
  orchestrator-to-worker delegation, such as an OfficeBench-compatible setup.
  LEGOMem becomes a mandatory baseline.
- If the work remains single-agent workflow memory, use a clean compositional
  environment such as ALFWorld or WebShop and remove multi-agent language from
  the title and claims.

AppWorld 1.x artifacts remain archival diagnostics only.  A new AppWorld study
would require independently fresh data custody, a fresh protocol, and separate
authorization; it is not an extension of the prior killed configuration.

### 5.4 Required experimental arms

The pilot uses the following minimum set:

| Arm | Memory content / policy | What it isolates |
|---|---|---|
| No memory | No retrieved experience | Whether any memory helps |
| Raw semantic trajectory RAG | Top retrieved prior trace under semantic similarity | Episodic semantic reuse |
| Semantic procedural memory | Same distilled procedure budget, no graph gate | Abstraction without structural screening |
| COPROMEM without veto | Schema extraction/retrieval but semantic candidate is always injected | Value of the veto itself |
| COPROMEM full | Schema extraction, typed alignment, veto, and matched retrieval budget | Proposed mechanism |

For a final paper, add one official, fidelity-checked representative baseline
from each relevant family:

- AWM or AutoGuide for workflow/contextual guidance;
- ReasoningBank or CONTRAMEM for experience-derived memory;
- LEGOMem for multi-agent procedural memory, if multi-agent is claimed; and
- a generic critic/Reflexion-like repair arm only for the supporting handoff
  diagnosis experiment.

Do not claim a comparison with a paper unless the implementation, prompt,
inputs, model budget, and deviations are documented.  A broken or weakened
adapter is not a baseline.

### 5.5 Metrics

Primary metrics are reported by structural regime and template cluster:

| Metric | Definition |
|---|---|
| Task success | Fraction of tasks accepted by the benchmark's native evaluator. |
| Negative-transfer rate (NTR) | \(P(Y_{memory}=0 \land Y_{no-memory}=1)\) on paired runs. |
| Structural transfer gain | Success difference between full COPROMEM and no-memory in low-semantic/high-structural cases. |
| Safe reuse precision | Fraction of reuse decisions whose schema is applicable and whose deployment does not harm the paired no-memory outcome. |
| Structural veto precision/recall | Accuracy of rejecting pre-labeled incompatible schemas. |

Secondary metrics:

- typed node/edge/obligation F1 on the controlled suite only;
- retrieved memory tokens, planner calls, environment actions, latency, and
  model cost;
- abstention rate and candidate diversity; and
- for RQ3 only, fault-label macro-F1, repair locality, recovery success, and
  regression on initially successful cases.

Use scenario/template-cluster bootstrap confidence intervals or an equivalent
cluster-aware analysis.  Do not count seeds, replays, edits, checkpoints, or
branches as independent tasks.

### 5.6 Decision gates

The following are prospective gates; exact numeric thresholds are registered
before test execution and may be calibrated only from development data.

| Gate | GO condition | KILL / REVISE condition |
|---|---|---|
| Headroom | Semantic RAG produces nontrivial, predeclared negative transfer on the development semantic-trap regime. | No measurable negative-transfer problem exists. |
| Representation | Extractor/alignment separates development structural regimes substantially better than semantic similarity alone. | Graph extraction is unreliable or merely reproduces semantic similarity. |
| Mechanism | Full method lowers held-out NTR versus raw RAG and no-veto under matched budget, with a confidence interval excluding no effect. | Effect is absent, unstable, or explained by more tokens/calls. |
| Transfer | Full method improves low-semantic/high-structural success without a compensating drop on high/high tasks. | Gains occur only where wording is also similar, or safety is lost. |
| External validity | Directionally consistent result on one fresh external benchmark. | Result survives only the controlled generator. |

No numerical result should be reclassified as success through parser repair,
post-hoc extraction, or changes to the denominator after outcomes are known.

---

## 6. Prior-work positioning

| Family | Relevant prior capability | COPROMEM 2.0 must demonstrate beyond it |
|---|---|---|
| ExpeL / Reflexion | Experience-derived textual lessons and reflection after outcomes | That typed structural veto yields a distinct, measured reduction in harmful reuse. |
| AutoGuide | Context-aware guidelines extracted from contrastive trajectory deviations | That graph alignment, not contextual text alone, identifies semantic--structural conflict. |
| AWM | Induced reusable workflows and selective use | That explicit compatibility/veto improves transfer safety under controlled mismatch. |
| ReasoningBank / CONTRAMEM | Success/failure-derived evolving reasoning or procedural memory | That the effect depends on typed structure and survives same-budget textual-memory controls. |
| ReMe / MemP | Procedural-memory distillation, refinement, deprecation, and lifecycle management | That separation is not simply another heuristic update/pruning rule. |
| LEGOMem | Modular memory across orchestrator and task agents | That structural compatibility at handoffs changes reuse quality, not merely memory placement. |
| ADaPT | Adaptive task decomposition at execution time | That persistent schemas beat re-decomposition specifically in the structural-transfer regime. |
| AgentSpec / Contract2Tool | Executable rules/contracts and runtime enforcement | That learned applicability and structural veto add value beyond fixed/manual rules. |

The paper must use conservative language: it proposes a candidate distinction and
tests it; it does not assert that all neighboring work lacks structure,
verification, memory refinement, or multi-agent support.

---

## 7. Relationship to the prior CoProMem/CoProCon record

### 7.1 Reusable assets

Reuse, after separate validation for the new setting:

- structured protocol/result storage and append-only accounting;
- isolated execution and native scoring patterns;
- paired original/intervention outcome accounting;
- harm-aware reporting with beneficial and harmful flips; and
- static/manual controls as mandatory competitors, not strawmen.

### 7.2 Evidence that cannot be promoted

Do not use the following as confirmation of COPROMEM 2.0:

- synthetic 6/6 or 26/32 gains from domain-authored rules;
- unstable GSM8K results or invalid ExpeL adaptation;
- local AppWorld program/block transplants;
- the binding-aware F821 checker result;
- the manual 8/11 selection ceiling;
- Cycle 24 strict 0/4 or Cycle 24B's post-hoc 2/4 teacher repairs; or
- counts of many branches, actions, calls, and replays as independent task
  evidence.

Those results are still valuable: they demonstrate why a clean split, strong
controls, native scoring, and separation of construction/selection/recovery are
necessary.

---

## 8. Implementation roadmap

### Stage A — paper-only specification

1. Freeze the schema grammar, alignment function, veto action, bank update
   rule, and information boundary.
2. Complete a primary-source novelty table for the nearest methods above.
3. Decide whether the claim is genuinely multi-agent.  If yes, select a
   role-handoff benchmark; if no, remove multi-agent framing.

### Stage B — controlled-suite construction

1. Implement the task/schema generator and independent surface paraphrase
   generator.
2. Version the generator seed, split assignment, hidden test release process,
   scorer, and graph labels.
3. Implement only no-memory, semantic RAG, no-veto, and full-method arms.
4. Run development-only feasibility gates; do not inspect test outcomes.

### Stage C — preregistered pilot

1. Freeze commit, prompts, model route, token/call caps, thresholds, and
   metrics.
2. Run all arms on the held-out controlled test exactly once per predeclared
   task/seed schedule.
3. Report every failure, refusal, parser error, cost, and harmful outcome in
   the original denominator.
4. Produce only GO / REVISE / KILL, then stop before adding benchmark adapters.

### Stage D — external confirmation

Only after a GO, port the frozen mechanism to one external benchmark and add
the appropriate official baseline(s).  Do not change the central method after
seeing external-benchmark results.

---

## 9. Detailed algorithmic specification

### 9.1 Data structures

The research implementation must make every learned or inferred object
inspectable.  The following JSON-compatible schema is the minimum persistent
record; implementations may add fields but may not hide model-produced logic in
unversioned prompt text.

```yaml
SchemaRecord:
  schema_id: stable content hash
  schema_version: integer
  family_id: development-only family label or inferred cluster ID
  node_types: [retrieve, filter, validate, rank, commit, delegate]
  edges:
    - source: node ID
      target: node ID
      handoff_type: typed artifact label
      required: true | false
  obligations:
    - edge_id: edge ID
      predicate_id: registry name
      required_public_fields: [field]
      fail_action: abstain | local_retry | request_upstream_artifact
  applicability:
    semantic_description: compact retrieval text
    positive_evidence_ids: [episode ID]
    separation_evidence_ids: [episode ID]
  extraction:
    extractor_version: hash
    prompt_hash: hash or null
    confidence: number in [0, 1]
  lifecycle:
    status: candidate | admitted | deprecated
    created_at: timestamp
    parent_schema_id: optional ID
```

```yaml
EpisodeRecord:
  episode_id: stable content hash
  task_id: opaque benchmark identifier
  split: train | dev | test
  public_task_view_digest: hash
  public_trace: typed, redacted observable events only
  extracted_schema_id: ID
  retrieved_schema_ids: [ID]
  vetoes:
    - candidate_schema_id: ID
      semantic_score: number
      structural_score: number
      reason_code: incompatible_edge | missing_obligation | low_confidence
  outcome:
    native_success: boolean
    actions: integer
    planner_calls: integer
    input_tokens: integer
    output_tokens: integer
  protocol_hash: hash
```

No field may contain hidden evaluator state, task gold answers, chain of thought,
or outcome labels that were unavailable to baseline arms at the corresponding
decision point.

### 9.2 Schema extraction procedure

Given public input \(I_x\), tool/API schema \(M_x\), and optional public plan
prefix \(P_x\), the extractor returns a schema proposal and confidence:

```text
EXTRACT-SCHEMA(I_x, M_x, P_x)
  1. Parse the allowed role/subtask vocabulary.
  2. Emit typed nodes that correspond to observable subtask commitments.
  3. Add an edge only when the target requires a typed artifact produced by
     the source under the public task/tool specification.
  4. Attach an obligation only from the verifier registry or a constrained
     predicate grammar; arbitrary generated code is forbidden.
  5. Validate acyclicity, node/edge types, field references, and public-input
     scope.  Reject malformed proposals rather than repairing them silently.
  6. Return the canonicalized schema, extraction confidence, and validation log.
```

The first implementation should use a small closed node/edge vocabulary.  An
open-ended graph language makes it impossible to tell whether a gain is due to
structure, extra natural-language guidance, or post-hoc human normalization.

### 9.3 Typed alignment procedure

For query graph \(Q\) and bank graph \(S\), alignment uses an injective
partial mapping \(\phi : V_Q \rightarrow V_S\).  A simple transparent score is:

\[
G(Q,S) = \max_{\phi}\frac{
w_V\,\mathrm{type\_match}_V +
w_E\,\mathrm{type\_match}_E +
w_C\,\mathrm{obligation\_match}_C -
w_M\,\mathrm{missing\_required\_edges}
}{w_V|V_Q| + w_E|E_Q| + w_C|C_Q|}.
\]

The exact weights and graph-matching approximation are frozen before test
execution.  Report node agreement, edge agreement, obligation agreement, and
missing-required-edge penalties separately.  A scalar score without these
components is insufficient evidence that the method used structure.

### 9.4 Retrieval and veto pseudocode

```text
RETRIEVE-OR-VETO(task x, bank B, budget b)
  Q, q, log <- EXTRACT-SCHEMA(public(x))
  candidates <- TOP-K-SEMANTIC(x, B, k, b)
  eligible <- []

  for S in candidates:
      r <- semantic_score(x, S)
      g, alignment_log <- TYPED-ALIGN(Q, S)
      if q < tau_q:
          record veto(S, r, g, low_confidence)
      else if g < tau_g:
          record veto(S, r, g, incompatible_structure)
      else:
          eligible.append((S, r, g, alignment_log))

  if eligible is empty:
      return NO_MEMORY, all_logs

  S_star <- rank eligible by fixed f(r, g, size(S))
  return S_star, all_logs
```

`NO_MEMORY` is a real abstention outcome, not permission to spend an additional
generation/replanning budget.  The no-veto ablation uses the same extracted
schema and candidate set, but selects the highest semantic candidate whenever
one exists.  Thus the only intended difference is the structural-veto decision.

### 9.5 Schema promotion and separation pseudocode

```text
UPDATE-BANK(development episode e, bank B)
  if e.split != development:
      abort
  if schema/trace validation fails:
      store rejected record; return B
  if e creates high-semantic / low-structural conflict:
      append separation evidence to candidate schema
  else:
      append positive or negative use evidence

  if predeclared independent-evidence threshold is met:
      branch or admit a schema according to frozen rule
  else:
      retain evidence in fast buffer only
  return B
```

Promotion must depend on independent development scenarios, never repetitions of
one scenario.  A test episode may be logged for analysis but never updates the
bank in the primary offline-transfer evaluation.

### 9.6 Handoff verification pseudocode

```text
VERIFY-HANDOFF(edge e, artifact a, schema S)
  obligation <- S.obligations[e]
  public_fields <- PROJECT(a, obligation.required_public_fields)
  result <- REGISTRY[obligation.predicate_id](public_fields)
  if result.pass:
      continue workflow
  else if obligation.fail_action == request_upstream_artifact:
      issue one pre-budgeted local request to source(e)
  else:
      abstain / continue according to the registered protocol
```

This procedure is deliberately narrower than arbitrary code repair.  It is an
auditable boundary check.  Any future code-generation or repair module must be
evaluated as a separate component with a matched no-record debugger and an
equal-compute retry control.

---

## 10. System architecture and implementation boundary

### 10.1 Components

```text
Public task/tool view
        │
        ├── Schema extractor ──> typed query schema
        │                              │
Memory bank ── semantic retriever ─────┼──> typed alignment + veto
        │                              │             │
        │                              │             ├── no-memory abstention
        │                              │             └── schema-conditioned planner
        │                              │
        └── evidence store <── handoff verifier <── workflow execution
                                       │
                                       └── development-only promotion/branching
```

The planner, retriever, schema extractor, verifier registry, evaluator, and
bank updater are separate modules with explicit input/output records.  This
separation is necessary to distinguish a retrieval improvement from a planner
upgrade or additional tool access.

### 10.2 Information parity

Every arm must use the same:

- base model/version, decoding parameters, prompt length cap, and total token
  cap;
- public task description, tools, API documentation, observation history, and
  allowed role messages;
- maximum planner/tool/environment calls and retry budget;
- native evaluator and stopping rule; and
- candidate source pool and retrieval count, where applicable.

COPROMEM alone may use typed alignment and a veto over its retrieved candidate;
it may not receive private graph labels, hidden task state, extra examples,
additional repair calls, or an unbounded context window.

### 10.3 Safety boundary

The schema verifier operates on public, typed artifacts only.  Model-generated
predicates are selected from a registered grammar and are interpreted in a
bounded worker.  They cannot access host files, network, credentials, hidden
benchmark state, arbitrary reflection text, or arbitrary Python execution.

The prior AppWorld sandbox/replay implementation is useful as a design pattern,
but it does not certify a new benchmark adapter.  Every new adapter needs its
own state-restoration, evaluator, and noninterference checks.

### 10.4 What is intentionally out of scope

COPROMEM 2.0 does not initially solve:

- universal causal discovery from traces;
- moral/legal blame or unique responsible-agent identification;
- unconstrained program synthesis or arbitrary patch generation;
- online test-set updating;
- hidden-state monitoring; or
- full lifelong-learning claims across open-ended environments.

Restricting scope is essential: these capabilities each have separate prior art
and would make the causal contribution of structural veto unidentifiable.

---

## 11. Full benchmark protocol

### 11.1 SchemaConflictBench

The controlled benchmark should be generated from a typed workflow grammar.
Each template creates task instances with a known latent dependency schema and
independently sampled surface realization.

| Dimension | Required design choice |
|---|---|
| Structure | At least four disjoint graph families, each with multiple valid surface realizations. |
| Semantics | Surface vocabulary/object domain independently randomized from graph family. |
| High semantic / low structure | Same surface family paired with conflicting prerequisite, validation, or ranking order. |
| Low semantic / high structure | Different surface domains realizing the same typed graph. |
| Gold labels | Generated from template metadata before any method run. |
| Evaluator | Deterministic native success predicate independent of the memory bank. |
| Split | Disjoint graph-template families or compositional combinations across train/dev/test. |

The benchmark must include no-memory-solvable semantic traps.  Otherwise a
veto can look beneficial simply because it refuses difficult tasks rather than
because it prevents a harmful memory injection.

### 11.2 Split and custody protocol

Before any model calls:

1. Generate and hash all candidate templates and split assignments.
2. Freeze train/dev/test seeds and make test contents inaccessible to method
   development.
3. Freeze the schema grammar, threshold calibration protocol, prompts, and
   baseline adapters using train/dev only.
4. Record every human author who can see each split and every code revision
   capable of reading it.
5. Open the test split only for the registered final run.

This is a correction to the prior AppWorld custody failure.  “Reserved” or
“not yet run” is not enough; the project needs affirmative evidence that test
content did not steer schema design or manual controls.

### 11.3 External benchmark selection protocol

Use a decision table before choosing the external adapter:

| Intended claim | Required setting | Minimum external evidence |
|---|---|---|
| Single-agent structural workflow memory | Compositional planning/tool benchmark | Held-out structural transfer and semantic-trap analysis with native scoring |
| Multi-agent handoff memory | Explicit orchestrator-worker/task-agent setting | Role-level messages/artifacts, delegation outcome, and matched LEGOMem-style control |
| Handoff verification | Benchmark exposing typed intermediate artifacts | Predeclared valid/invalid boundary examples and initially successful cases for harm measurement |

Do not select a benchmark merely because an adapter already exists.  The
benchmark must expose the mechanism needed for the paper's claim.

### 11.4 Statistical analysis plan

For every primary contrast, report:

- per-template-family task success and NTR;
- paired difference, cluster-aware 95% confidence interval, and task-family
  denominator;
- beneficial, harmful, and neutral paired changes where paired executions are
  meaningful;
- all completed and failed model/tool attempts, including malformed outputs;
- input/output tokens, calls, environment actions, latency, and cost; and
- an arm-by-regime interaction: the structural-veto effect should be larger in
  high-semantic/low-structural cases than in high/high cases.

Predeclare one primary hypothesis test: full COPROMEM versus semantic RAG on
NTR in the semantic-trap regime.  Other metrics are secondary or diagnostic;
they must not be promoted after observing a weak primary result.

---

## 12. Baseline fidelity and ablation plan

### 12.1 Baseline tiers

| Tier | Methods | Purpose |
|---|---|---|
| Mechanism controls | No memory, raw semantic RAG, semantic procedural memory, no-veto COPROMEM | Establish whether structural veto itself matters. |
| Memory competitors | One fidelity-checked method from AWM/AutoGuide; one from ReasoningBank/CONTRAMEM; ReMe or MemP when lifecycle is claimed | Compare with modern procedural/contextual memory. |
| Decomposition competitor | ADaPT; LEGOMem if and only if the paper makes a multi-agent claim | Separate persistent structure from fresh/adaptive decomposition and memory placement. |
| Diagnosis controls | Generic critic and reflection baseline only in RQ3 | Separate structural boundary checks from generic feedback. |

The controlled pilot may begin with Tier 1.  A final submission cannot claim
superiority over a family whose representative method was not run or whose
adapter is known to be broken.

### 12.2 Baseline cards

Each implemented comparison requires a versioned card:

```yaml
BaselineCard:
  paper: title, authors, year, URL
  official_code_revision: hash or unavailable
  implementation_status: official | faithful adaptation | paper-based reimplementation
  changed_components: [environment, model, prompts, retrieval, evaluator]
  information_budget: task fields, trace fields, memory fields
  compute_budget: calls, tokens, tools, retries
  deviations_and_rationale: text
  validation: smoke tests and known limitations
```

No result may be called an “exact reproduction” without running the original
method in its intended environment under its documented dependencies.

### 12.3 Essential ablations

| Ablation | Fixed components | Removed component | Predicted diagnostic |
|---|---|---|---|
| Semantic-only retrieval | Same bank/candidates/budget | Typed alignment and veto | Higher NTR on semantic traps |
| No-veto schema retrieval | Same extractor and schema text | Veto decision | Shows whether extraction alone is enough |
| Random graph | Same prompt/token size | Correct graph structure | Tests whether graph markup merely provides extra tokens |
| No handoff contracts | Same retrieved schema | Boundary obligation verification | More invalid downstream propagation on RQ3 only |
| Immediate update | Same evidence and bank budget | Fast-buffer promotion delay | Higher regression only if RQ4 is studied |

The random-graph control is important.  Without it, graph-conditioned prompts
could outperform textual memory merely because they force a more deliberate
planning format, not because their graph is correct.

---

## 13. Historical evidence register: CoProMem and CoProCon 1.x

This section records the prior project accurately so that its artifacts can be
reused without misrepresentation.

| Phase | What changed | Main observed result | Interpretation for COPROMEM 2.0 |
|---|---|---|---|
| Synthetic CoPro | Domain-authored executable guards for join/count tasks | CoPro/static 26/32 versus no memory 13/32; tiny 6/6 versus 3/6 | Retain as regression fixture only; not automatic induction evidence. |
| GSM8K prototype | Textual/schematic memory versus no-memory/success-only | Direction and magnitude unstable across repeats; literature adaptation had AWM 17/20 versus CoPro 16/20 and invalid ExpeL handling | Do not use for efficacy or baseline claims. |
| C1--C4 | Frozen checkpoints and contrast/admission tests | No learned advantage; C2/C3 produced zero admitted bank candidates under their protocol | New method needs a representation that separates task structure, not just outcome variation. |
| C5--C11 | AppWorld runtime, source collection, interface/horizon changes | Bounded replay works; early collection had 0/8 successes; later source successes exist but are sparse and inspected | Retain harness lessons, not source data as clean test material. |
| C12--C18 | Crossover, block transplant, input binding | Two local repair effects; many candidates failed due to missing context/bindings | Typed artifact boundaries matter, but ordinary program repair remains a competing explanation. |
| C19--C22 | Predicates, public observation, static checking | AST-count representation collided across contextual outcomes; static B solved measured missing-name labels | New structural representation must beat static/manual controls under equal input. |
| Post-C22 | Manual selector and teacher repair diagnostic | Manual selector equals 8/11 quality oracle; C24 strict 0/4, C24B post-hoc 2/4 local improvements | Do not revisit activation on the eleven pairs or promote C24B into learned-memory evidence. |

### 13.1 Historical claims that remain safe

- Bounded saved-prefix replay and native scoring can be made auditable on the
  supported environment subset.
- Interface/output formatting improvements do not establish task competence.
- Local repairs and a successful intervention do not imply a transferable
  learned schema.
- Static/manual controls can remove apparent headroom that a learned method was
  presumed to have.
- Harm must be measured on initially successful tasks, not inferred from a
  failure-only repair set.

### 13.2 Historical claims that are closed or unsupported

- The old AppWorld allocation is not a clean held-out study.
- No learned activation selector can improve strictly over the 8/11 oracle on
  the fixed candidate pairs.
- CoProCon 1.x did not demonstrate an admitted stateful learned contract bank.
- The project did not demonstrate prospective cross-scenario transfer,
  multi-agent responsibility attribution, or learned-contract superiority.

---

## 14. Reproducibility, accounting, and reporting requirements

### 14.1 Required artifacts per experiment

```text
protocol.json              frozen split, models, budgets, hypotheses
source_manifest.json       source/task lineage and hashes
schema_bank.json           every admitted/candidate/deprecated schema
retrieval_log.jsonl        all candidates, scores, alignment and vetoes
execution_log.jsonl        task actions and public observations
outcome_report.json        native scores and paired outcomes
cost_ledger.json           calls, attempts, tokens, reservations, settlements
baseline_cards/            fidelity cards for every comparator
analysis_script/           deterministic report generation
```

Raw responses should be retained under access controls where benchmark licenses
and privacy rules allow.  Public artifacts should avoid credentials, secrets,
hidden benchmark state, and chain-of-thought disclosure.

### 14.2 Cost accounting

Report at least:

- completed calls and all attempts separately;
- input, output, cached, and reasoning tokens where the provider exposes them;
- settled spend and conservative unresolved reservation separately;
- local compute/environment operations separately from provider cost; and
- cost per scenario, per success, and per beneficial intervention.

An equal maximum call cap is not automatically equal compute.  The report must
show actual realized usage by arm.

### 14.3 Result labels

Use only these labels:

| Label | Meaning |
|---|---|
| Supported | Directly measured inside its stated implementation/sample boundary. |
| Preliminary | Local signal with plausible alternatives or inadequate independent units. |
| Inconclusive | Required comparison/evidence is missing. |
| Falsified | Contradicted for the exact predeclared formulation/sample. |
| Not tested | Proposed but not executed. |
| Killed configuration | Cannot continue under the documented evidence/custody/budget constraints. |

A parser failure, a failed transport attempt, a post-hoc sensitivity analysis,
and a negative native outcome are different facts.  They must remain separate in
both tables and prose.

---

## 15. Claim discipline for an AAMAS submission

### Claims permitted only after positive evidence

- Typed structural compatibility improves safe procedural reuse under semantic
  conflict.
- Structural veto reduces negative transfer under matched information and
  compute.
- Persistent schema memory transfers across low-semantic/high-structural tasks.
- Handoff obligations improve local boundary-fault handling in the stated
  benchmark setting.

### Claims not permitted without separate evidence

- First/only structural memory system.
- General causal discovery or causal blame assignment.
- General multi-agent improvement from single-agent benchmarks.
- General safety from zero observed harms on failure-only tasks.
- Automatic contract induction from an LLM-generated schema alone.
- Superiority over a prior method that was not faithfully reproduced or
  information/compute matched.

---

## 16. Success criterion

The project is successful only if it can support the following precise statement:

> On held-out workflow scenarios with pre-labeled semantic--structural
> conflict, COPROMEM's graph-conditioned retrieval reduces negative transfer
> and preserves structural transfer relative to semantic trajectory/procedural
> memory and a no-veto ablation under the same model, public information,
> retrieval budget, tool access, and evaluator.

If the controlled test does not support that statement, the right outcome is
not a larger system.  It is a revised or terminated formulation with the
negative result retained.

---

## 17. References and internal evidence

### Primary literature to audit before a submission

- ExpeL: <https://arxiv.org/abs/2308.10144>
- AutoGuide: <https://arxiv.org/abs/2403.08978>
- AWM: <https://arxiv.org/abs/2409.07429>
- Reflexion: <https://arxiv.org/abs/2303.11366>
- ReasoningBank: <https://arxiv.org/abs/2509.25140>
- CONTRAMEM: <https://arxiv.org/abs/2608.22533>
- MemP: <https://arxiv.org/abs/2508.06433>
- ReMe: <https://arxiv.org/abs/2512.10696>
- LEGOMem: <https://arxiv.org/abs/2510.04851>
- ADaPT: <https://arxiv.org/abs/2311.05772>
- AgentSpec: <https://arxiv.org/abs/2503.18666>
- Contract2Tool: <https://arxiv.org/abs/2606.07904>

### Internal evidence governing this specification

- [Research status report](../research/STATUS_REPORT_2026-09-16.md)
- [Claim--evidence ledger](../research/CLAIM_EVIDENCE_LEDGER_2026-09-16.md)
- [Primary-source novelty audit](../research/NOVELTY_MATRIX_20260916.md)
- [Procedural-graphs novelty correction](../research/052_PROCEDURAL_GRAPHS_NOVELTY_UPDATE.md)
- [COPROMEM 2.0 idea sketch](COPROMEM_2.0_IDEA.md)
- [Benchmark and baseline inventory](COPROMEM_2.0_benchmarks.md)
- [Focused experiment plan](COPROMEM_2.0_top4_novelty_experiment_plan.md)
