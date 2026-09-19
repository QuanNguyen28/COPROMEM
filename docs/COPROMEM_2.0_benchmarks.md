# COPROMEM 2.0 — Benchmark & Baseline Summary

## 1. Recommended Benchmarks

| Benchmark | Why it is suitable for COPROMEM 2.0 | Main research question(s) answered | Key measurements |
|---|---|---|---|
| **ALFWorld** | Repeated compositional task structures make structural reuse easy to inspect. Cheap enough for large ablations and continual-learning experiments. | **RQ1:** Does structural memory transfer across tasks? **RQ5:** Does stored decomposition improve planning? **RQ8:** Does memory improve with experience? | Task success, transfer gain, decomposition depth, planner calls, steps to success, schema reuse accuracy |
| **WebShop** | Tasks can be lexically similar while differing in constraints, ranking objectives, and verification requirements. Excellent for misleading semantic similarity. | **RQ2:** Does pattern separation prevent negative transfer? **RQ3:** Do handoff contracts prevent premature decisions? **RQ6:** Does anti-lock-in retrieval help? | Negative transfer rate, constraint violations, schema reuse precision, handoff violation rate, retrieval diversity |
| **Mind2Web** | Cross-task, cross-website, and cross-domain splits provide a natural gradient from surface similarity to structural generalization. | **RQ1:** Is COPROMEM learning reusable structure rather than website-specific traces? **RQ5:** Does structure help under distribution shift? | Success by split, transfer gain, schema retrieval accuracy, cross-domain degradation, memory efficiency |
| **WebArena** | Long-horizon closed-loop web tasks stress workflow reuse, dependencies, replanning, and functional completion. | **RQ1:** Does structural memory help in realistic environments? **RQ5:** Does learned structure reduce replanning? **RQ7:** Are gains efficient? | Functional success, action count, planner calls, token cost, latency, dependency failures |
| **AppWorld** | API-driven tasks naturally contain explicit dependencies, state transitions, preconditions, and handoffs. Best standard benchmark for structural credit assignment. | **RQ3:** Can COPROMEM distinguish handoff, dependency, scope, and leaf failures? **RQ5:** Does DAG memory improve execution? | Failure attribution accuracy, dependency accuracy, repair precision, state-based success, unintended side effects |
| **MemoryAgentBench** | Standardized memory evaluation covering retrieval, test-time learning, long-range understanding, and selective forgetting. | **RQ4:** Does CLS-style consolidation maintain useful memory while avoiding interference? **RQ8:** Does memory remain stable as it grows? | Retrieval accuracy, forgetting/selective retention, memory growth, regression rate |
| **TravelPlanner** *(optional)* | Strong constraint satisfaction and multi-stage planning make handoff contracts and validation checkpoints easy to test. | **RQ1:** Does task-structure memory transfer? **RQ3:** Do contracts prevent invalid downstream planning? | Constraint satisfaction, budget violations, dependency errors, plan validity |
| **OfficeBench** *(optional, multi-agent)* | Closest setting for comparing orchestrator-level and executor-level memory against LEGOMem. | **RQ1:** Does explicit decomposition-schema memory outperform modular procedural memory? **RQ3:** Do contracts improve delegation? | Task success, delegation errors, handoff violations, planner/executor memory usefulness |
| **SWE-bench** *(later-stage stress test)* | Real software issues contain rich dependency structures, but coding/tool noise can obscure whether memory is the true cause. | **External validity:** Does structural memory transfer to complex software engineering tasks? | Patch success, localization quality, planner calls, test pass rate, token cost |
| **Structural Transfer Suite / SchemaTransferBench** *(custom)* | Controlled 2×2 design: same/different semantics × same/different structure. Directly isolates structural transfer and pattern separation. | **RQ1:** Can COPROMEM transfer structure despite low semantic similarity? **RQ2:** Can it reject misleading memories despite high semantic similarity? | Structural-transfer accuracy, pattern-separation accuracy, negative transfer rate, schema reuse precision/recall |

---

## 2. Recommended Baselines

| Baseline | Why compare against it | Main question answered by comparison | Key measurements |
|---|---|---|---|
| **ReAct / No Memory** | Minimal lower bound. | Does memory help at all? | Task success, steps, tokens |
| **Raw Trajectory RAG** | Simplest memory strategy: retrieve similar previous trajectories. | Is structural abstraction better than episodic memorization? | Success, retrieved tokens, negative transfer, memory growth |
| **Reflexion** | Strong verbal failure/reflection baseline. | Is structural failure attribution better than generic textual reflection? | Failure recovery, attribution accuracy, regression after repair |
| **ReasoningBank** | Strong success/failure reasoning-memory competitor. | Is remembering task structure more useful than remembering reusable reasoning strategies? | Transfer gain, negative transfer, memory efficiency, low-semantic/high-structural transfer |
| **AWM** | Strong reusable workflow-memory baseline. | Do explicit DAG dependencies, contracts, and scope conditions outperform workflow templates? | Success, dependency errors, cross-domain transfer, planner calls |
| **ReMe** | Strong dynamic procedural-memory lifecycle baseline with refinement/pruning. | Is explicit structural memory useful beyond sophisticated procedural-memory management? | Success, regression rate, memory size, update stability |
| **LEGOMem** | Closest memory + decomposition competitor: coarse memory aids orchestration while fine memory aids task agents. | Does treating decomposition itself as a persistent structured object outperform modular procedural memory? | Delegation success, schema reuse, handoff violations, decomposition quality |
| **ADaPT** | Closest recursive decomposition baseline; decomposes further when execution is difficult. | Does remembering successful factorization outperform decomposing from scratch every time? | Planner calls, depth, steps, task success, token cost |
| **AdaPlan-H** | Adaptive coarse-to-fine planning baseline. | Should decomposition granularity depend only on task complexity, or also on accumulated experience? | Granularity, success, planner cost, reuse rate |
| **SkillWeaver / Compositional Skill Routing** | Close decompose → retrieve → compose competitor using skill-aware iterative decomposition. | Does lifelong structural memory add value beyond aligning subtasks with available skills? | Success, decomposition quality, schema persistence, transfer reliability |

---

## 3. COPROMEM 2.0 Ablations

| Ablation | What is removed or replaced | Question answered | Key measurements |
|---|---|---|---|
| **− Pattern Separation** | Remove semantic-vs-structural conflict detection. | Is pattern separation responsible for lower negative transfer? | Negative transfer rate, scope mismatch rate |
| **− Handoff Contracts** | Remove verifier gates between subtasks. | Do contracts prevent downstream propagation of invalid intermediate results? | Handoff violation rate, cascading failures |
| **− Structural Credit Assignment** | Replace four-tier diagnosis with generic reflection. | Does localized blame improve repair quality and reduce regressions? | Attribution accuracy, repair precision, regression rate |
| **− CLS Fast/Slow Memory** | Update slow memory immediately after each episode. | Does delayed consolidation reduce catastrophic interference? | Old-task retention, regression, schema stability |
| **− Prioritized Replay** | Replace prioritized replay with random/frequency replay. | Does prioritized replay select more useful experiences for consolidation? | Retention, sample efficiency, consolidation cost |
| **− Anti-Lock-in Retrieval** | Replace diverse/counter-schema retrieval with standard top-1 retrieval. | Does anti-lock-in retrieval improve robustness under distribution shift? | Retrieval diversity, dominant-schema escape rate, success after shift |
| **− Structural Retrieval** | Retrieve using semantic similarity only. | Does structural retrieval improve correct schema selection? | Schema reuse precision/recall, negative transfer |

---

## 4. Controlled Mechanism Tests

| Controlled experiment | Setup | COPROMEM mechanism being tested | Main question | Key measurements |
|---|---|---|---|---|
| **Structural Transfer Test** | Same structure, different semantics. | Structural schema retrieval | Does COPROMEM retrieve by task structure rather than wording? | Transfer gain, correct schema retrieval |
| **Semantic Trap Test** | Same semantics, different structure. | Pattern separation | Can COPROMEM reject a misleadingly similar schema? | Negative transfer rate, separation accuracy |
| **Injected Handoff Error** | Corrupt data passed from one valid subtask to another. | Handoff contracts + credit assignment | Can COPROMEM recognize a handoff violation? | Attribution accuracy, repair locality |
| **Injected Dependency Error** | Delete or alter a required DAG dependency. | Structural credit assignment | Can COPROMEM distinguish dependency failure from execution failure? | Dependency diagnosis accuracy, repair precision |
| **Injected Scope Error** | Force retrieval of a semantically similar but structurally incompatible schema. | Pattern separation + scope diagnosis | Can COPROMEM identify incorrect schema applicability? | Scope-error accuracy, negative transfer |
| **Injected Leaf Error** | Keep structure correct but force a local executor mistake. | Four-tier credit assignment | Can COPROMEM avoid unnecessarily modifying the global schema? | Leaf-error accuracy, schema preservation |
| **Continual Interference Stream** | Train on structure A, inject rare A′ anomalies, return to A, then later make A′ frequent. | CLS fast/slow memory + pattern separation | Can COPROMEM resist outliers while still learning genuine new variants? | Retention on A, learning of A′, schema branching, regression |
| **Retrieval Lock-in Shift** | A historically dominant schema becomes wrong under a changed context. | Anti-lock-in retrieval | Can the agent escape a dominant historical schema? | Success after shift, plan diversity, dominant-schema escape rate |
| **Memory Growth Test** | Continuously add tasks and schemas over a long stream. | Consolidation and pruning | Does COPROMEM remain stable as memory grows? | Success vs memory size, retrieval latency, duplicate rate, schema stability |

---

## 5. Evaluation Metrics

### 5.1 Overall Task Performance

| Metric | What it measures | Why it matters |
|---|---|---|
| **Task Success Rate** | Fraction of completed tasks | Overall agent ability |
| **Transfer Gain** | `SR_memory − SR_no-memory` | Benefit obtained from accumulated experience |
| **Steps to Success** | Number of environment actions until completion | Execution efficiency |
| **Planner Calls** | Number of decomposition/replanning calls | Whether stored schemas reduce repeated planning |
| **Tokens / Latency** | Inference cost and runtime | Whether performance gains are computationally reasonable |

### 5.2 Structural-Memory Quality

| Metric | What it measures | Why it matters |
|---|---|---|
| **Schema Reuse Precision** | Fraction of reused schemas that were actually applicable | Detects harmful reuse |
| **Schema Reuse Recall** | Fraction of reusable cases where the correct schema was found | Measures missed transfer opportunities |
| **Pattern-Separation Accuracy** | Correctly separating semantically similar but structurally incompatible tasks | Direct test of pattern separation |
| **Dependency Accuracy** | Precision/recall/F1 of DAG edges | Measures correctness of learned task structure |
| **Decomposition Fidelity** | Whether solving all children actually satisfies the parent task | Ensures the decomposition preserves task semantics |
| **Handoff Violation Rate** | Fraction of inter-node transfers violating contracts | Measures effectiveness of handoff verification |

### 5.3 Failure and Repair Quality

| Metric | What it measures | Why it matters |
|---|---|---|
| **Failure Attribution Accuracy** | Accuracy over Handoff / Dependency / Scope / Leaf labels | Directly tests four-tier structural credit assignment |
| **Repair Precision / Locality** | Whether only the responsible component is modified | Measures whether repair avoids collateral changes |
| **Recovery Success Rate** | Fraction of diagnosed failures successfully repaired | Tests practical value of diagnosis |
| **Regression Rate** | Previously solved tasks that become unsolved after memory update | Measures catastrophic interference |

### 5.4 Continual-Memory Quality

| Metric | What it measures | Why it matters |
|---|---|---|
| **Schema Stability / Survival** | Persistence of still-valid schemas over time | Tests slow-memory stability |
| **Memory Growth** | Number/tokens of stored memory objects vs experience count | Measures scalability |
| **Duplicate / Contradiction Rate** | Redundant or conflicting schemas in memory | Tests consolidation quality |
| **Memory Efficiency** | Transfer gain per retrieved-memory token | Controls for larger context budgets |
| **Performance vs Memory Age** | Utility of old schemas as time passes | Measures long-term retention |
| **Performance vs Bank Size** | Task success as memory grows | Detects retrieval degradation |

### 5.5 Exploration and Retrieval Diversity

| Metric | What it measures | Why it matters |
|---|---|---|
| **Retrieval Diversity** | Structural diversity among retrieved schemas | Tests anti-lock-in behavior |
| **Dominant-Schema Escape Rate** | Probability of switching away from a historically dominant but currently wrong schema | Direct test of lock-in robustness |
| **Alternative Plan Diversity** | Number/structural diversity of plausible plans explored | Detects over-constrained reasoning |

---

## 6. Research Questions

| ID | Research question | Best benchmark / experiment | Most important baseline |
|---|---|---|---|
| **RQ1 — Structural Transfer** | Does memory of task structure transfer better than memory of complete solutions, textual lessons, or workflows? | ALFWorld, Mind2Web, Structural Transfer Test | Raw RAG, ReasoningBank, AWM |
| **RQ2 — Negative Transfer** | Does pattern separation prevent reuse of semantically similar but structurally incompatible memories? | WebShop, Semantic Trap Test | Raw RAG, ReasoningBank, AWM |
| **RQ3 — Structural Credit Assignment** | Can COPROMEM correctly localize handoff, dependency, scope, and leaf failures and repair only the responsible component? | AppWorld, Injected Failure Tests | Reflexion, ReasoningBank |
| **RQ4 — Continual Learning** | Does fast/slow consolidation reduce catastrophic interference? | MemoryAgentBench, Continual Interference Stream | ReMe, immediate-update COPROMEM |
| **RQ5 — Decomposition Quality** | Does persistent decomposition memory outperform reconstructing task decomposition from scratch? | ALFWorld, AppWorld, WebArena | ADaPT, AdaPlan-H, LEGOMem |
| **RQ6 — Retrieval Lock-in** | Does anti-lock-in retrieval preserve useful alternatives under distribution shift? | WebShop, Retrieval Lock-in Shift | Top-1 retrieval, AWM |
| **RQ7 — Efficiency** | Are gains due to better memory representation rather than more model calls or tokens? | All benchmarks | Equal-budget versions of all baselines |
| **RQ8 — Scaling** | Does performance remain stable as experience and memory-bank size grow? | ALFWorld streams, Memory Growth Test | ReMe, Raw RAG, AWM-online |

---

## 7. Recommended Compact Evaluation Setup

| Purpose | Recommended choice |
|---|---|
| **Main benchmarks** | ALFWorld, WebShop, AppWorld, Structural Transfer Suite |
| **Generalization benchmark** | Mind2Web |
| **Realistic expensive benchmark** | WebArena |
| **Memory-specific benchmark** | MemoryAgentBench |
| **Core baselines** | ReAct, Raw Trajectory RAG, ReasoningBank, AWM, ADaPT, COPROMEM 2.0 |
| **Additional strong baselines** | ReMe, LEGOMem, AdaPlan-H, SkillWeaver |
| **Essential ablations** | −Pattern Separation, −Handoff Contracts, −Structural Credit Assignment, −CLS, −Prioritized Replay, −Anti-Lock-in |
| **Signature controlled tests** | Structural Transfer, Semantic Trap, Injected Failure, Continual Interference, Retrieval Lock-in |
| **Most important claims to prove** | Structural transfer, lower negative transfer, accurate structural fault attribution, reduced catastrophic interference, improved decomposition reuse |
