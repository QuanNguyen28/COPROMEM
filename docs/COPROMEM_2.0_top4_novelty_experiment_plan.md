# COPROMEM 2.0 — Focused Experiment Plan for the 4 Highest-Novelty Research Questions

## 0. Why these four RQs were selected

The original evaluation contained eight research questions. For a stronger and more focused paper, the four below are the most important because they test the parts of COPROMEM 2.0 that are least reducible to standard procedural memory or adaptive decomposition.

| Priority | Selected RQ | Why it is high-novelty for COPROMEM 2.0 | Closest prior-art pressure |
|---|---|---|---|
| **1** | **RQ1 — Structural Transfer** | Tests the core claim that the reusable memory object should be **task structure / decomposition schema**, not merely a prior solution, textual lesson, or workflow. | AWM, MemP, LEGOMem, ReasoningBank already cover workflows/procedures/reasoning memory, so COPROMEM must show transfer based on structure itself. |
| **2** | **RQ2 — Negative Transfer & Pattern Separation** | Tests whether COPROMEM can distinguish tasks that look semantically similar but require different causal/dependency structures. This directly targets a weakness of similarity-based retrieval. | Existing RAG/procedural-memory systems retrieve similar experience, but explicit structural pattern separation is less central in the closest methods. |
| **3** | **RQ3 — Structural Credit Assignment** | Tests whether failures can be localized to **handoff, dependency, scope, or leaf execution** rather than producing generic reflection or globally rewriting memory. | Reflexion, ReasoningBank, and ReMe learn from failure, but the proposed structural fault taxonomy and localized repair are more specific. |
| **4** | **RQ4 — Continual Structural Memory Stability** | Tests the CLS-inspired fast/slow memory idea: rare anomalies should not immediately corrupt stable schemas, while recurring genuine variants should eventually be consolidated. | ReMe/MemP update procedural memory, but selective slow consolidation of structural schemas under interference is a stronger differentiator. |

### RQs intentionally moved to secondary analysis

| Original RQ | Why it is not a primary novelty question |
|---|---|
| **RQ5 — Decomposition Quality** | Important, but adaptive decomposition is already crowded by ADaPT, AdaPlan-H, HiAgent, LEGOMem, and skill-aware decomposition work. Treat it as a supporting metric for RQ1 rather than a headline claim. |
| **RQ6 — Retrieval Lock-in** | Interesting, but better positioned as a robustness ablation supporting RQ2/RQ4 rather than a standalone contribution. |
| **RQ7 — Efficiency** | Necessary for fairness, but efficiency is an evaluation constraint rather than the central scientific novelty. |
| **RQ8 — Scaling** | Important, but best treated as part of continual-memory stability under RQ4. |

---

# 1. RQ1 — Structural Transfer

## Research question

> **Does storing and retrieving task structure as a decomposition schema transfer better than storing complete trajectories, textual reasoning memories, or workflow templates when surface semantics change but the underlying task structure is preserved?**

## Core hypothesis

For two tasks \(T_a\) and \(T_b\):

\[
Sim_{semantic}(T_a,T_b) \text{ can be low}
\]

while:

\[
Sim_{structural}(G_a,G_b) \text{ is high},
\]

where \(G\) is the task's dependency/decomposition graph.

COPROMEM should outperform semantic/trajectory memory most strongly in this regime.

## Primary benchmarks

| Benchmark | Role in RQ1 | Why selected |
|---|---|---|
| **ALFWorld** | Controlled compositional transfer | Repeated reusable structures such as find → pick → modify → place make structural reuse easy to inspect. |
| **Mind2Web** | Cross-task / cross-website / cross-domain transfer | Tests whether structure transfers when website and vocabulary change. |
| **SchemaTransferBench — Structural Transfer split** | Mechanism-isolation benchmark | Explicitly pairs tasks with different semantics but equivalent dependency structures. |
| **AppWorld** | Tool/API structural transfer | Tests whether DAG structure transfers across different API/task surfaces. |

## Baselines

| Baseline | What comparison answers |
|---|---|
| **ReAct / No Memory** | Is prior experience useful at all? |
| **Raw Trajectory RAG** | Is structural abstraction better than episodic retrieval? |
| **ReasoningBank** | Is task-structure memory better than distilled reasoning memory? |
| **AWM** | Is explicit decomposition/dependency structure better than reusable workflow memory? |
| **LEGOMem** | Is a first-class decomposition schema better than modular procedural memory supporting planning? |
| **ADaPT** | Does reusable structural memory outperform rediscovering task decomposition from scratch? |
| **COPROMEM 2.0** | Proposed method |

## Experimental conditions

| Condition | Description | Desired behavior |
|---|---|---|
| **A** | Same semantics, same structure | Reuse schema |
| **B** | Different semantics, same structure | **Transfer structurally** |
| **C** | Novel structure | Do not force an old schema |

Example for the main condition:

```text
Task A: choose the cheapest valid product
Task B: choose the cheapest eligible travel option
```

Shared abstract structure:

```text
generate candidates
→ verify hard constraints
→ rank valid candidates
→ commit
```

## Metrics

| Metric | Purpose |
|---|---|
| **Task Success Rate** | Overall performance |
| **Transfer Gain** | Improvement over no-memory agent |
| **Schema Reuse Precision** | Whether reused schemas were valid |
| **Schema Reuse Recall** | Whether reusable structural matches were found |
| **Structural Transfer Accuracy** | Correct reuse on low-semantic/high-structural pairs |
| **Dependency Edge F1** | Whether the transferred DAG is structurally correct |
| **Planner Calls** | Whether reuse avoids re-decomposition |
| **Memory Tokens Retrieved** | Fairness / efficiency control |

## Evidence needed

The strongest result is that COPROMEM's advantage is largest specifically on:

\[
\text{low semantic similarity} + \text{high structural similarity}.
\]

If gains occur only when both wording and structure are similar, evidence for structural memory is weak.

---

# 2. RQ2 — Negative Transfer and Pattern Separation

## Research question

> **Can COPROMEM prevent harmful reuse when two tasks are semantically similar but require different causal/dependency structures?**

## Core hypothesis

Similarity-only retrieval tends to make:

\[
Sim_{semantic}(T_a,T_b) \uparrow
\Rightarrow
P(reuse) \uparrow
\]

even when structural distance is large.

COPROMEM should explicitly branch or veto reuse in these cases.

## Primary benchmarks

| Benchmark | Role in RQ2 | Why selected |
|---|---|---|
| **WebShop** | Natural semantic traps | Product-selection tasks can look nearly identical while constraints or objectives require different procedures. |
| **SchemaTransferBench — Semantic Trap split** | Clean mechanism test | Same-semantics/different-structure pairs with known schema assignments. |
| **Mind2Web** | Real web generalization | Tests whether inappropriate website workflows are rejected despite semantic similarity. |
| **AppWorld** | Tool/API scope mismatch | Allows controlled wrong-schema injection. |

## Baselines

| Baseline | What comparison answers |
|---|---|
| **Raw Trajectory RAG** | How bad is pure semantic retrieval under structural mismatch? |
| **ReasoningBank** | Do reasoning memories avoid the same negative-transfer traps? |
| **AWM** | Does workflow retrieval distinguish structurally incompatible but similar tasks? |
| **ReMe** | Can context-adaptive procedural memory avoid the mismatch? |
| **LEGOMem** | Does modular procedural memory prevent scope mismatch? |
| **COPROMEM − Pattern Separation** | Is pattern separation itself responsible for the gain? |
| **COPROMEM 2.0** | Proposed method |

## Controlled 2×2 design

| Semantic similarity | Structural similarity | Desired behavior |
|---|---|---|
| High | High | **Reuse** |
| High | Low | **Separate / veto reuse** |
| Low | High | **Transfer structurally** |
| Low | Low | **Do not reuse** |

The crucial RQ2 condition is:

\[
\text{High semantic similarity + Low structural similarity}.
\]

## Metrics

| Metric | Purpose |
|---|---|
| **Negative Transfer Rate** | Memory causes a failure that no-memory would avoid |
| **Pattern-Separation Accuracy** | Whether misleadingly similar tasks are correctly split |
| **Scope-Mismatch Rate** | Applying a schema outside its valid context |
| **Schema Reuse Precision** | Whether reuse decisions are safe |
| **Veto Precision / Recall** | Accuracy of rejecting an inappropriate schema |
| **Task Success Rate** | End-to-end effect |
| **Retrieval Diversity** | Supporting anti-lock-in analysis |

Define:

\[
NTR = P(fail\ with\ memory \land succeed\ without\ memory).
\]

## Evidence needed

COPROMEM should specifically show:

\[
NTR_{COPROMEM} < NTR_{semantic-memory\ baselines}
\]

on semantic-trap tasks.

The pattern-separation ablation should remove much of this advantage.

---

# 3. RQ3 — Structural Credit Assignment

## Research question

> **When a task fails, can COPROMEM identify whether the root cause is a handoff violation, dependency conflict, scope mismatch, or leaf execution error, and repair only the responsible component?**

## Core hypothesis

COPROMEM attempts:

\[
Failure
\rightarrow
\{Handoff,\ Dependency,\ Scope,\ Leaf\}
\rightarrow
LocalizedRepair.
\]

If correct, this should improve recovery while reducing collateral regression.

## Primary benchmarks

| Benchmark | Role in RQ3 | Why selected |
|---|---|---|
| **AppWorld** | Main benchmark | Explicit APIs, state transitions, and dependencies allow precise error injection and verification. |
| **WebArena** | Realistic confirmation | Tests whether localization survives noisier long-horizon environments. |
| **SchemaTransferBench — Fault Injection split** | Controlled causal validation | Each task contains exactly one injected known structural fault. |

## Baselines

| Baseline | What comparison answers |
|---|---|
| **Generic LLM Critic** | Can a normal critic diagnose the same failures without structural memory? |
| **Reflexion** | Is structural attribution more precise than verbal reflection? |
| **ReasoningBank** | Are failure-derived reasoning memories sufficient? |
| **ReMe** | Does dynamic failure-aware procedural memory localize errors equally well? |
| **COPROMEM − Structural Credit Assignment** | Is the explicit four-tier mechanism necessary? |
| **COPROMEM 2.0** | Proposed method |

## Controlled fault injection

Start from a known-valid DAG:

```text
T1 → T2 → T3 → T4
```

| Fault | Injection | Ground-truth class |
|---|---|---|
| **F1** | Corrupt output passed from T1 to T2 | **Handoff violation** |
| **F2** | Delete a required edge T2 → T3 | **Dependency conflict** |
| **F3** | Force retrieval/use of a similar but invalid schema | **Scope mismatch** |
| **F4** | Keep DAG correct but force T4 to issue a wrong local action/API argument | **Leaf execution error** |

## Metrics

| Metric | Purpose |
|---|---|
| **Failure Attribution Accuracy** | Main classification accuracy over four tiers |
| **Per-Class F1** | Detects whether one class dominates |
| **Repair Precision / Locality** | Whether only the responsible component is modified |
| **Recovery Success Rate** | Whether diagnosis enables successful repair |
| **Regression Rate** | Whether repair breaks previously solved tasks |
| **Unnecessary Schema Mutation Rate** | Whether leaf errors incorrectly modify global structure |
| **Repair Cost** | Extra calls/tokens/actions needed to recover |

## Evidence needed

A strong result must show all three:

1. higher attribution accuracy;
2. higher recovery success;
3. lower regression after repair.

The intended mechanism is:

```text
better structural attribution
→ more localized repair
→ less unnecessary memory rewriting
→ fewer regressions
```

---

# 4. RQ4 — Continual Structural Memory Stability

## Research question

> **Does the fast/slow CLS-inspired memory design prevent rare or noisy experiences from corrupting stable decomposition schemas while still allowing genuinely recurring new structures to be learned?**

## Core hypothesis

Immediate online consolidation can cause:

```text
new unusual episode
→ immediately modifies global schema
→ previously valid tasks regress
```

COPROMEM instead uses:

```text
Fast Episodic Buffer
→ Prioritized Replay
→ Slow Consolidated Schema Bank
```

with conceptual replay priority:

\[
Priority = Need \times Gain \times (1 + Surprise) \times (1 + Uncertainty).
\]

## Primary benchmarks

| Benchmark | Role in RQ4 | Why selected |
|---|---|---|
| **ALFWorld continual stream** | Cheap repeated structural learning | Allows hundreds/thousands of sequential experiences. |
| **MemoryAgentBench** | Auxiliary memory-quality test | Evaluates retention, learning, and forgetting behavior. |
| **SchemaTransferBench — Interference Stream** | Main causal test | Precisely controls stable schemas, anomalies, and genuine distribution shifts. |

## Baselines

| Baseline | What comparison answers |
|---|---|
| **Immediate-update COPROMEM** | Does fast/slow separation matter? |
| **FIFO Episodic Memory** | Is replay/consolidation better than simple recency? |
| **Random Replay** | Is prioritization useful? |
| **Frequency-Based Replay** | Is full prioritization better than frequency alone? |
| **AWM-online** | How does online workflow learning behave under interference? |
| **ReMe** | Can dynamic procedural-memory refinement provide comparable stability? |
| **MemP** | Does repository updating/deprecation handle interference equally well? |
| **COPROMEM 2.0** | Proposed method |

## Core continual-learning stream

Use two related but structurally distinct schema families:

\[
A,\quad A'
\]

| Phase | Stream | Desired behavior |
|---|---|---|
| **1** | 100 examples from A | Learn stable schema A |
| **2** | 5 rare examples from A′ | Keep A′ episodic; do not corrupt A |
| **3** | 100 more examples from A | A performance should remain stable |
| **4** | 50–100 examples from A′ | Pattern-separate and consolidate A′ |

## Metrics

| Metric | Purpose |
|---|---|
| **Retention on A** | Whether rare A′ experiences damage the stable schema |
| **Learning Rate on A′** | Whether the system eventually learns the new variant |
| **Regression Rate** | Previously solved A tasks that fail after updates |
| **Schema Branching Accuracy** | Whether A′ becomes a separate schema instead of corrupting A |
| **Consolidation Delay** | Episodes required before a new structure enters slow memory |
| **Old/New Task Balance** | Stability–plasticity tradeoff |
| **Memory Growth** | Whether stability is achieved through uncontrolled duplication |
| **Replay Cost** | Computational cost of consolidation |
| **Performance vs Bank Size** | Retrieval scalability |

## Replay ablation

Compare:

```text
No replay
Random replay
Frequency replay
Surprise-only replay
Need × Gain
COPROMEM full priority
```

## Evidence needed

The desired behavior is:

```text
Rare-anomaly phase:
COPROMEM retains A better than immediate-update methods

True distribution-shift phase:
COPROMEM still learns A′ rather than freezing permanently
```

The claim is therefore a better **stability–plasticity tradeoff**, not merely less forgetting.

---

# 5. Compact Benchmark Matrix

| Benchmark / Test | RQ1 Structural Transfer | RQ2 Pattern Separation | RQ3 Credit Assignment | RQ4 Continual Stability |
|---|:---:|:---:|:---:|:---:|
| **ALFWorld** | ★★★ | ★ | ★ | ★★★ |
| **WebShop** | ★★ | ★★★ | ★ | ★ |
| **Mind2Web** | ★★★ | ★★ | ★ | ★ |
| **AppWorld** | ★★★ | ★★ | ★★★ | ★ |
| **WebArena** | ★★ | ★★ | ★★ | ★ |
| **MemoryAgentBench** | ★ | ★ | – | ★★★ |
| **SchemaTransferBench** | ★★★ | ★★★ | ★★★ | ★★★ |

---

# 6. Recommended Minimal Experimental Suite

| Purpose | Recommended benchmark |
|---|---|
| **Compositional structural transfer** | **ALFWorld** |
| **Negative transfer / semantic traps** | **WebShop** |
| **Structural fault attribution** | **AppWorld** |
| **Controlled mechanism validation** | **SchemaTransferBench** |
| **Optional cross-domain validation** | **Mind2Web** |

This core set directly targets novelty better than running many unrelated leaderboards.

---

# 7. Minimal Baseline Set

| Baseline | Why it must remain |
|---|---|
| **ReAct / No Memory** | Lower bound |
| **Raw Trajectory RAG** | Episodic-memory control |
| **ReasoningBank** | Success/failure reasoning-memory competitor |
| **AWM** | Workflow-memory competitor |
| **ReMe** | Dynamic procedural-memory competitor |
| **LEGOMem** | Closest memory + decomposition competitor |
| **ADaPT** | Decomposition-from-scratch competitor |
| **COPROMEM 2.0** | Proposed method |

### Specialized baselines

| Baseline | Use primarily for |
|---|---|
| **Reflexion** | RQ3 |
| **MemP** | RQ4 |
| **AdaPlan-H** | Supporting decomposition analysis under RQ1 |
| **SkillWeaver / Compositional Skill Routing** | Skill-aware decomposition/retrieval comparison |

---

# 8. Essential Ablations

| Ablation | Primary RQ | Expected failure if mechanism matters |
|---|---|---|
| **− Structural Retrieval** | RQ1 | Lower transfer under semantic shift |
| **− Pattern Separation** | RQ2 | Higher negative transfer on semantic traps |
| **− Handoff Contracts** | RQ3 | More propagation of invalid intermediate states |
| **− Structural Credit Assignment** | RQ3 | Lower fault localization, more unnecessary repairs |
| **− CLS Fast/Slow Memory** | RQ4 | Higher regression after rare anomalies |
| **− Prioritized Replay** | RQ4 | Worse consolidation efficiency/stability |
| **− Anti-Lock-in Retrieval** | Supporting RQ2/RQ4 | More persistent reuse of dominant but outdated schemas |

---

# 9. Primary Metrics by RQ

| RQ | Primary metrics | Secondary metrics |
|---|---|---|
| **RQ1 Structural Transfer** | Structural Transfer Accuracy, Transfer Gain, Schema Reuse Precision/Recall | Task Success, Dependency Edge F1, planner calls |
| **RQ2 Pattern Separation** | Negative Transfer Rate, Pattern-Separation Accuracy, Scope-Mismatch Rate | Veto precision/recall, retrieval diversity |
| **RQ3 Structural Credit Assignment** | Failure Attribution Accuracy, Repair Locality, Regression Rate | Recovery success, repair cost, unnecessary schema mutation |
| **RQ4 Continual Stability** | Old-task Retention, Regression Rate, Schema Branching Accuracy, A′ Learning Rate | Consolidation delay, replay cost, memory growth |

---

# 10. Main-Paper Experiment Order

| Experiment | Datasets | Main baselines | Primary evidence |
|---|---|---|---|
| **E1 — Structural Transfer** | SchemaTransferBench + ALFWorld + Mind2Web | Raw RAG, ReasoningBank, AWM, LEGOMem, ADaPT | COPROMEM transfers across low-semantic/high-structural pairs |
| **E2 — Pattern Separation** | SchemaTransferBench + WebShop | Raw RAG, ReasoningBank, AWM, ReMe | COPROMEM lowers negative transfer on semantic traps |
| **E3 — Structural Fault Attribution** | AppWorld + controlled fault injection | Generic critic, Reflexion, ReasoningBank, ReMe | COPROMEM localizes faults and repairs with fewer regressions |
| **E4 — Continual Structural Memory** | SchemaTransferBench interference stream + ALFWorld stream | Immediate update, random/frequency replay, AWM-online, ReMe, MemP | COPROMEM retains A while eventually learning A′ |

---

# 11. Paper-Level Evidence Chain

```text
RQ1:
COPROMEM transfers across low-semantic / high-structural task pairs
        ↓
Evidence that the bank captures TASK STRUCTURE

RQ2:
COPROMEM rejects high-semantic / low-structural matches
        ↓
Evidence that structural memory avoids NEGATIVE TRANSFER

RQ3:
COPROMEM correctly localizes injected structural faults
and repairs only responsible components
        ↓
Evidence for STRUCTURAL CREDIT ASSIGNMENT

RQ4:
COPROMEM survives rare anomalies without corrupting stable schemas,
yet learns recurring new variants
        ↓
Evidence for FAST/SLOW STRUCTURAL CONSOLIDATION
```

Together, these answer the central paper question:

> **Can an agent learn, distinguish, repair, and continually consolidate reusable task structures rather than merely storing prior solutions?**

---

# 12. Headline Claims — Only If Supported

| Claim | Required evidence |
|---|---|
| **Persistent decomposition schemas enable structural transfer across semantically different tasks.** | RQ1 |
| **Joint semantic–structural retrieval reduces negative transfer between semantically similar but structurally incompatible tasks.** | RQ2 |
| **Structural credit assignment localizes failures and reduces collateral memory updates compared with generic reflective repair.** | RQ3 |
| **Fast episodic storage plus selective consolidation improves the stability–plasticity tradeoff of lifelong structural memory.** | RQ4 |

If any effect is not demonstrated, weaken or remove the corresponding headline claim rather than relying on aggregate success rate.
