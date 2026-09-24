# Memory and Decomposition for LLM Agents: Detailed Paper Summary and Comparison

**Prepared:** 2026-09-17  
**Scope:** Papers searched in the recent literature review on agent memory, procedural memory, task decomposition/hierarchical planning, and neuroscience/human-memory mechanisms relevant to designing a stronger memory–decomposition agent.

> **Reading guide.** This report focuses on *mechanisms*, not just benchmark scores. For every method, the main questions are:
> 1. What is stored or learned?
> 2. At what abstraction/granularity?
> 3. How is it retrieved?
> 4. How is it updated?
> 5. Does it use failures?
> 6. Does it learn task decomposition, or only execute a decomposition generated at run time?
> 7. How close is it to the current research direction: **learning reusable procedural memories plus reusable decomposition knowledge, with adaptive decomposition based on executability and transfer reliability?**

---

## 1. Executive comparison

### 1.1 Agent memory methods

| Paper | Venue/status | Core memory object | Success / failure use | Memory update | Decomposition relation | Main idea in one sentence | Overlap with current direction |
|---|---|---|---|---|---|---|---|
| **ReasoningBank** | ICLR 2026 | Distilled reusable reasoning strategies | **Both** successful and failed trajectories | Continuous extraction + consolidation | Indirect; memories can affect future reasoning, but decomposition itself is not the central learned object | Convert trajectories into generalizable reasoning memories and improve them through memory-aware test-time scaling | **High** for success/failure lesson memory; lower for persistent learned decomposition structure |
| **ReMe** | Findings ACL 2026 | Fine-grained procedural experiences, success patterns, failure triggers, comparative insights | **Both** | Utility-based validate/add/prune/refine | Indirect | Treat procedural memory as a full lifecycle: distill, contextually adapt, validate, prune | **High** for dynamic procedural-memory lifecycle |
| **MemP** | Findings ACL 2026 | Fine-grained step instructions + higher-level script abstractions | Mainly distilled trajectory procedures; repository can be corrected/deprecated | Build/retrieve/update repository | Higher-level scripts can resemble decomposed procedures | Explicitly studies how to build, retrieve, update lifelong procedural memory at multiple granularities | **High** for multi-granularity procedural memory |
| **LEGOMem** | AAMAS 2026 | Reusable trajectory-derived memory units allocated to orchestrator/task agents | Primarily reusable past-task traces/procedures | Modular memory placement/retrieval | **Directly supports decomposition at orchestrator level** | Put coarse procedural memory at the orchestrator for decomposition/delegation and fine memory at task agents for execution | **Very high** for multi-agent memory + decomposition; important novelty constraint |
| **Agent Workflow Memory (AWM)** | ICML 2025 | Reusable workflows/routines induced from successful task examples | Mostly successful/useful routines | Offline or online induction | Workflows encode common subtask/action structure | Infer reusable workflows and inject relevant ones into new tasks | **High** if current method stores successful workflows; lower if learning failures/decomposition reliability |
| **ExpeL** | AAAI 2024 | Natural-language insights + past experiences | Learns from experiential task set; includes comparisons between experience outcomes | Insight extraction/refinement | Indirect | Convert accumulated experiences into reusable natural-language knowledge without weight updates | **Medium–high** for experience-to-lesson memory |
| **Synapse** | ICLR 2024 | Complete abstracted trajectories as exemplars | Demonstration trajectories | Retrieval by similarity | No learned decomposition | Store whole trajectories and retrieve similar exemplars after state abstraction | **Medium**; less abstract than current procedural/decomposition-memory idea |
| **Reflexion** | NeurIPS 2023 | Verbal self-reflections in episodic buffer | Strong emphasis on failure feedback and self-correction | Add reflective feedback across trials | No persistent decomposition learning | Turn task feedback into verbal reflection that conditions later attempts | **Medium**; failure memory overlaps, but memory is less structured and less procedural |
| **RecMem** | Findings ACL 2026 | Consolidated recurrent interaction patterns + recovered fine details | Recurrent information rather than task success/failure as primary signal | Recurrence-triggered consolidation | No central decomposition mechanism | Consolidate only recurring semantic clusters to reduce memory construction cost | **Medium** for selective consolidation |
| **MemPO** | Findings ACL 2026 | Agent-generated summaries of task-relevant memory | Credit assignment based on memory effectiveness | Policy learns what to summarize/retain | Not primarily decomposition | Optimize the agent's own memory-management policy so retained memory aligns with long-horizon task reward | **Medium**; relevant to learned retention/credit assignment |
| **EMA** | Findings ACL 2026 | Episodic Memory Units (EMUs) | Not chiefly success/failure | MemDecider filters useful units | No | Segment conversation into episodic units and selectively retrieve/filter them | **Low–medium** for procedural task memory, useful for segmentation ideas |
| **SkillWeaver (web self-improvement)** | arXiv 2025 preprint | Executable reusable skills/APIs distilled from practice | Successful practiced skills are verified/honed | Iterative exploration expands/refines library | Skills can be composed | Explore a site, invent practice tasks, execute them, and compile robust trajectories into callable APIs | **High** if current method creates executable skills |
| **Demystify the Role of Memory in MLE Agents** | Findings ACL 2026 | Experimental study rather than a new memory representation | N/A | N/A | Compares memory impact under chain vs tree search | Memory can stabilize chain agents but reduce search diversity in tree-based agents | **Important design warning**: memory can cause premature search/decomposition convergence |

### 1.2 Decomposition / hierarchical planning methods

| Paper | Venue/status | How decomposition is produced | When refinement happens | Persistent decomposition memory? | Main contribution | Overlap with current direction |
|---|---|---|---|---|---|---|
| **ADaPT** | Findings NAACL 2024 | Recursive LLM decomposition | **As needed when a subtask cannot be executed** | **No** | Match decomposition depth to executor capability | **Very high** for executability-triggered decomposition; low for learned cross-task decomposition memory |
| **AdaPlan-H** | Findings ACL 2026 | Coarse macro plan progressively refined | Based on estimated task complexity | No explicit reusable decomposition-memory repository | Adaptive planning granularity instead of fixed granularity | **High** for adaptive granularity |
| **HiAgent** | ACL 2025 | LLM formulates subgoals | During execution; working memory summarized by subgoal | No cross-task learned decomposition structure | Use subgoals as hierarchical chunks to compress in-trial memory | **High** for subgoal-based hierarchy; lower for lifelong cross-task learning |
| **LLMCompiler** | ICML 2024 | Planner builds dependency/execution graph of tool calls | Dynamic replanning from executor feedback | No | Exploit dependency structure to parallelize function calling | **Medium**; relevant to decomposition graph and dependency-aware execution |
| **Decomposed Prompting** | ICLR 2023 | Prompted decomposition into specialist subtasks | Can recursively decompose difficult subtasks | No learned decomposition memory | Modular subproblem delegation to specialized prompts/models/functions | **Medium** baseline for modular decomposition |
| **Least-to-Most Prompting** | ICLR 2023 | Generate simpler subproblems, then solve sequentially | Fixed two-stage procedure | No | Easy-to-hard compositional reasoning | **Medium** baseline for decomposition |
| **Compositional Skill Routing / “SkillWeaver”** | arXiv 2026 preprint | Decompose query into atomic subtasks, retrieve skills, compose DAG | **Skill-aware iterative feedback** improves granularity | The skill library is persistent; decomposition itself is iteratively adapted but not clearly a learned cross-task decomposition schema | Retrieval-aware decomposition explicitly aligns subtask granularity with available skills | **Very high** for decompose–retrieve–compose and retrieval-conditioned refinement |

### 1.3 Neuroscience / human-memory mechanisms

| Mechanism | Representative papers | Empirical idea | Agent-design analogue | Why it matters |
|---|---|---|---|---|
| **Complementary Learning Systems (CLS)** | McClelland et al. 1995; O'Reilly et al. 2011; McClelland et al. 2020 | Fast episodic learning and slow integration/generalization reduce interference | Separate fast trajectory store from slower consolidated procedural/schema memory | Avoid immediately overwriting global procedures with one noisy episode |
| **Prioritized replay** | Mattar & Daw 2018 | Replay is prioritized by expected decision utility (“need × gain”) | Consolidate/replay memories based on expected future usefulness, not frequency alone | Gives a principled memory-update priority |
| **Schema learning** | Tse et al. 2007, 2011 | New information integrates rapidly when compatible with an existing schema | Insert new procedural/decomposition knowledge into compatible schemas; branch when incompatible | Supports fast transfer without forcing all tasks into one template |
| **Event boundaries / segmentation** | Radvansky & Zacks 2017; DuBrow 2024 review | Continuous experience is segmented into events around prediction/context changes | Detect boundary points in trajectories to define reusable subtask chunks | A stronger basis for decomposition-memory extraction than arbitrary step windows |
| **Pattern separation / completion** | Yassa & Stark 2011; Liu et al. 2016 review | Similar episodes need distinct representations; partial cues can reconstruct stored patterns | Separate superficially similar procedures when their causal preconditions differ; retrieve a full procedure from partial task cues | Directly targets negative transfer/interference |
| **Reconsolidation** | Schwabe et al. 2014; Elsey et al. 2018 | Reactivated memories can become modifiable, though human evidence has boundary conditions | Update a retrieved memory after use instead of append-only correction | Natural mechanism for editing memory in context |
| **Retrieval-induced forgetting** | Murayama et al. 2014 meta-analysis | Repeated retrieval can suppress competing memories | Retrieval can bias an agent toward a narrow strategy family; intentionally decay competitors or preserve diversity | Explains why memory can reduce exploration |
| **Successor representation** | Momennejad et al. 2017 | Predictive representation caches expected future state occupancy, between model-free and model-based extremes | Store expected downstream subtask/skill transitions rather than only complete workflows | Enables flexible recomposition from partial structure |
| **Prospective memory** | Rummel & Kvavilashvili 2023 review | Remembering intended future actions requires cue-sensitive retrieval and coordination with ongoing behavior | Store subgoals with explicit triggering conditions, not just descriptions | Makes procedures conditional and execution-aware |

---

# 2. Detailed summaries: procedural and experiential memory

## 2.1 ReasoningBank — *Scaling Agent Self-Evolving with Reasoning Memory*

**Source:** ICLR 2026.  
Official paper/repository:  
- https://openreview.net/forum?id=jL7fwchScm  
- https://github.com/google-research/reasoning-bank

### Central idea

ReasoningBank argues that storing raw trajectories or only successful workflows misses the most reusable part of experience: **generalizable reasoning strategies**, including lessons extracted from failures.

After an interaction trajectory is complete:

1. the trajectory is judged,
2. successful or failed behavior is interpreted,
3. high-level reusable reasoning is distilled,
4. those reasoning memories are indexed,
5. future agents retrieve relevant memories,
6. new experience is then folded back into the bank.

A second component, **Memory-aware Test-Time Scaling (MaTTS)**, deliberately creates more/diverse trajectories, which provide richer contrastive evidence for memory extraction.

### Representation

The public description characterizes each memory item with fields such as:

- title,
- short description,
- detailed content / reasoning strategy.

The important point is that the stored unit is **not the original trajectory**. It is a compressed strategic lesson.

### What makes it different

Compared with workflow memory, it can extract:

- a strategy from success,
- a warning from failure,
- preventative reasoning,
- higher-level decision rules that apply outside one exact action sequence.

### Relation to the current research idea

**Strong overlap:**
- learns from successful and failed trajectories;
- stores high-level reusable knowledge;
- retrieves knowledge before/while solving new tasks;
- continuously accumulates experience.

**Remaining gap:**
- the primary persistent object is a **reasoning strategy**, not an explicit learned **task decomposition schema**;
- it does not center on learning whether a *particular factorization of a task* transfers reliably across contexts;
- it does not explicitly model decomposition boundaries as reusable memory objects with preconditions, subtask dependencies, and reliability.

### Novelty warning

Any proposal whose main claim is simply:

> “Use both successful and failed trajectories to distill reusable reasoning memories”

is no longer novel after ReasoningBank.

---

## 2.2 ReMe — *Remember Me, Refine Me: A Dynamic Procedural Memory Framework for Experience-Driven Agent Evolution*

**Source:** Findings of ACL 2026.  
https://aclanthology.org/2026.findings-acl.829/

### Central idea

ReMe targets the weakness of **passive append-only memory**. Its memory lifecycle has three major stages:

1. **Multi-faceted distillation**
   - extract success patterns;
   - identify failure triggers;
   - generate comparative insights.

2. **Context-adaptive reuse**
   - historical lessons are adapted/indexed to the new scenario instead of pasted verbatim.

3. **Utility-based refinement**
   - validated memories are added;
   - low-value or outdated memories are removed;
   - the memory remains compact.

### Key conceptual shift

Memory is treated as an **evolving knowledge base**, not a log.

This matters because a naive lifelong agent can accumulate:
- duplicated rules,
- contradictory rules,
- obsolete instructions,
- failure-specific warnings that become overgeneralized.

ReMe explicitly attacks this lifecycle problem.

### Relation to the current research idea

**Strong overlap:**
- success + failure information;
- comparative learning;
- dynamic updating;
- pruning;
- contextual adaptation.

**Potential distinction still available:**
- make the learned object a *decomposition policy/schema* rather than a generic procedural lesson;
- learn **where to split** a task based on experience;
- explicitly represent decomposition reliability and interference between alternate decompositions.

### Novelty warning

“Add utility scores, prune old procedural memories, and refine them using success/failure” is already largely covered by ReMe.

---

## 2.3 MemP — *Exploring Agent Procedural Memory*

**Source:** Findings ACL 2026.  
https://aclanthology.org/2026.findings-acl.866/

### Central idea

MemP studies procedural memory as a repository with multiple abstraction levels.

It distills trajectories into:

- **fine-grained step-by-step instructions**, and
- **higher-level script-like abstractions**.

It then studies three core operations:

- **Build**
- **Retrieval**
- **Update**

The memory can be:
- corrected,
- refined,
- deprecated,
- migrated across models.

### Important observation

MemP shows that procedural memory generated by a stronger model can benefit a weaker model. This suggests that external procedural memory can act as a transferable capability layer.

### Relation to decomposition

Higher-level scripts resemble decomposed task recipes, but MemP's focus is primarily **procedural memory**, not an explicit theory of:
- optimal subtask boundaries,
- alternate decompositions,
- dependency structures,
- factorization reliability.

### Relation to current research

This is one of the strongest prior-art constraints if the current idea is:

> store both low-level procedures and high-level task scripts.

That alone is not enough.

A stronger contribution needs a qualitatively different learned variable, such as:
- event boundary model,
- context-specific decomposition graph,
- decomposition uncertainty,
- structural credit assignment,
- pattern-separation decision over competing procedure schemas.

---

## 2.4 LEGOMem — *Modular Procedural Memory for Multi-agent LLM Systems for Workflow Automation*

**Source:** AAMAS 2026.  
https://doi.org/10.65109/VLUA1303

### Central idea

LEGOMem asks **where memory should live in a multi-agent architecture**.

Past trajectories are decomposed into reusable memory units, then allocated to:

- an **orchestrator**, which needs memory useful for planning/decomposition/delegation;
- specialized **task agents**, which benefit from finer execution-oriented memories.

### Key result

The paper reports that:
- orchestrator memory is important for task decomposition and delegation;
- fine-grained task-agent memory improves execution accuracy.

### Why this is especially close

LEGOMem already establishes the intuition:

> different hierarchical levels should retrieve different forms of procedural memory.

Therefore, a proposal that simply says:

> “retrieve high-level memory for task decomposition and low-level memory for subtasks”

has significant overlap.

### What it does *not* appear to center on

The central contribution is not:
- learning decomposition boundaries from failure contrast;
- explicit memory of alternative decomposition structures;
- causal structural credit assignment for which split caused success;
- interference-aware separation between similar-but-incompatible task structures;
- replay-based offline reorganization of decomposition knowledge.

Those are more promising gaps.

---

## 2.5 Agent Workflow Memory (AWM)

**Source:** ICML 2025.  
https://proceedings.mlr.press/v267/wang25bx.html

### Central idea

AWM induces **reusable workflows** from previous examples and retrieves them for later tasks.

It supports:
- **offline** induction from training examples;
- **online** induction during test-time experience.

The stored object is closer to a **routine** or **workflow template** than an entire raw trajectory.

### Why it works

Long-horizon tasks contain recurring action patterns. Reusing a workflow:
- reduces redundant planning;
- shortens action sequences;
- helps cross-task/domain transfer.

### Limitation relative to a learned decomposition theory

A workflow is an answer to:

> “What sequence/routine tends to work?”

A decomposition schema should additionally answer:

> “Why should this task be split *here*, under which conditions, into which dependency structure, and when should that structure not be reused?”

This distinction is crucial for novelty.

---

## 2.6 ExpeL — *LLM Agents Are Experiential Learners*

**Source:** AAAI 2024.  
https://doi.org/10.1609/aaai.v38i17.29936

### Central idea

ExpeL demonstrates non-parametric experiential learning:
- gather agent experiences,
- extract natural-language insights,
- retrieve relevant insights/experiences later.

Its central contribution is that an agent can improve from a growing pool of experience **without model fine-tuning**.

### Memory abstraction

ExpeL occupies a middle ground:
- more abstract than raw trajectory replay;
- less explicitly structured than later procedural-memory systems such as ReMe/MemP.

### Importance for novelty

Any new system based on “extract text lessons from many previous tasks and retrieve them” should be compared against ExpeL.

---

## 2.7 Synapse — *Trajectory-as-Exemplar Prompting with Memory for Computer Control*

**Source:** ICLR 2024.  
https://proceedings.iclr.cc/paper_files/paper/2024/hash/52f050499cf82fa8efb588e263f6f3a7-Abstract-Conference.html

### Central idea

Synapse makes full trajectories usable as in-context examples by combining:

1. **state abstraction** — remove irrelevant parts of complex computer state;
2. **trajectory-as-exemplar prompting** — use complete action trajectories;
3. **exemplar memory** — retrieve trajectories by similarity.

### Key difference from procedural-memory methods

Synapse largely preserves a demonstration as an exemplar.

ReasoningBank/ReMe/MemP instead transform the trajectory into reusable abstract knowledge.

### Relevance

Synapse is useful as the “low-abstraction memory” baseline:
- strong when new tasks closely resemble prior examples;
- potentially brittle when surface similarity hides different causal structure.

---

## 2.8 Reflexion — *Language Agents with Verbal Reinforcement Learning*

**Source:** NeurIPS 2023.  
https://proceedings.neurips.cc/paper_files/paper/2023/hash/1b44b878bb782e6954cd888628510e90-Abstract-Conference.html

### Central idea

After receiving feedback, an agent generates **verbal reflection** and stores it in an episodic buffer. Later attempts condition on these reflections.

### Why it matters historically

Reflexion established a simple but powerful principle:

> learning across attempts does not require weight updates; a language model can improve by storing verbal feedback about its own mistakes.

### Difference from newer memory systems

Reflexion generally does not provide:
- a large structured lifelong repository;
- multi-level procedural scripts;
- explicit consolidation/pruning;
- learned decomposition schemas.

It is still a strong baseline for **failure-aware memory**.

---

## 2.9 RecMem — *Recurrence-based Memory Consolidation for Efficient and Effective Long-Running LLM Agents*

**Source:** Findings ACL 2026.  
https://aclanthology.org/2026.findings-acl.1619/

### Central idea

Instead of extracting memory from everything, RecMem uses **recurrence** as a signal that a semantic cluster is worth consolidating.

The method also includes refinement to recover fine-grained details lost during extraction.

### Relevance to new ideas

The important design lesson is:

> memory importance does not need to be estimated only by success or similarity; *repetition/recurrence* can be an independent consolidation trigger.

A new decomposition memory could analogously consolidate a structural pattern only after:
- repeated recurrence,
- repeated successful transfer,
- or high expected future utility.

---

## 2.10 MemPO — *Self-Memory Policy Optimization for Long-Horizon Agents*

**Source:** Findings ACL 2026.  
https://aclanthology.org/2026.findings-acl.1166/

### Central idea

MemPO makes memory management part of the learned policy.

Rather than relying only on an external memory system, the agent learns to:
- summarize,
- retain,
- discard,
- manage memory according to task effectiveness.

The paper explicitly frames this as a **credit-assignment** problem over memory.

### Relevance

This suggests a more advanced direction than heuristic storage:

> assign credit not only to actions, but to *which memory representation/decomposition decision* caused later success.

That is a promising bridge to decomposition learning.

---

## 2.11 EMA — *An Episodic Memory Agent for Efficient and Selective Memory*

**Source:** Findings ACL 2026.  
https://aclanthology.org/2026.findings-acl.250/

### Central idea

EMA compresses conversational history into **Episodic Memory Units (EMUs)** and uses a **MemDecider** to select/filter which memories should influence generation.

### Relevance

The important analogy is **segmentation before retrieval**:
- do not store/retrieve one undifferentiated stream;
- first identify coherent episodic units.

This connects naturally to event segmentation in cognitive neuroscience.

---

## 2.12 SkillWeaver — *Web Agents can Self-Improve by Discovering and Honing Skills*

**Status:** arXiv preprint, 2025.  
https://arxiv.org/abs/2504.07079

### Central idea

The agent explores an environment, invents/practices useful tasks, and compiles successful behaviors into **reusable executable APIs**.

This is stronger than text-only procedural memory because the final memory is an **actionable skill**.

### Memory form

- executable code/API,
- metadata/verification,
- learned skill repertoire.

### Novelty implication

A new proposal cannot rely on “turn trajectories into callable reusable skills” as its sole novelty.

A more novel layer could govern:
- when skills should be separated or merged,
- how task structures predict compositions of skills,
- how failure changes skill boundary/schema,
- how the agent identifies latent task structure independently of one website.

---

# 3. Detailed summaries: decomposition and hierarchical planning

## 3.1 ADaPT — *As-Needed Decomposition and Planning with Language Models*

**Source:** Findings NAACL 2024.  
https://aclanthology.org/2024.findings-naacl.264/

### Central idea

ADaPT does **not always decompose everything**.

Instead:

1. attempt to execute a task/subtask;
2. if the executor cannot execute it,
3. recursively decompose it into simpler subtasks;
4. continue until the leaves become executable.

### Important conceptual contribution

The “correct” decomposition depth depends on:
- task complexity,
- executor capability.

Thus, decomposition is not an absolute property of the task.

### Strong overlap with current direction

If the current proposal says:

> “decompose a task further when the current subtask is not directly executable”

then ADaPT is the primary comparison and prior-art constraint.

### Remaining opportunity

ADaPT does not primarily learn from prior tasks:

- which decomposition worked best,
- which split failed,
- how reliable that decomposition is in related contexts,
- whether a different agent/model requires a different hierarchy.

A **lifelong decomposition memory** could go beyond ADaPT if it learns those variables explicitly.

---

## 3.2 AdaPlan-H — *From Coarse to Fine: Self-Adaptive Hierarchical Planning for LLM Agents*

**Source:** Findings ACL 2026.  
https://aclanthology.org/2026.findings-acl.77/

### Central idea

Planning begins with a coarse macro plan. The hierarchy is progressively refined according to task complexity.

### Difference from ADaPT

- **ADaPT:** refine because execution fails / is not directly possible.
- **AdaPlan-H:** refine coarse planning according to task complexity and adaptive planning needs.

Both reject fixed granularity.

### Novelty implication

“Adaptive decomposition depth” by itself is now crowded. A new method needs to say **what new information determines the boundary**.

Possible distinct signals:
- learned structural uncertainty,
- transfer reliability,
- memory interference,
- event-boundary prediction,
- causal credit for split decisions.

---

## 3.3 HiAgent — *Hierarchical Working Memory Management for Solving Long-Horizon Agent Tasks with Large Language Model*

**Source:** ACL 2025.  
https://aclanthology.org/2025.acl-long.1575/

### Central idea

HiAgent uses **subgoals as memory chunks**.

During a long trajectory:
- formulate subgoals;
- keep detailed action-observation history only for the active subgoal;
- summarize completed subgoal information;
- replace old low-level history with compressed subgoal summaries.

### Key contribution

Hierarchy is used to solve an **in-trial working-memory problem**.

### Difference from cross-trial procedural memory

HiAgent asks:

> “How should the current trajectory be compressed while it is unfolding?”

ReasoningBank/MemP/ReMe ask:

> “What should be learned across multiple task attempts?”

A new approach can combine these, but simple combination is not enough for strong novelty.

---

## 3.4 LLMCompiler — *An LLM Compiler for Parallel Function Calling*

**Source:** ICML 2024.  
https://proceedings.mlr.press/v235/kim24y.html

### Central idea

LLMCompiler converts a problem into an execution structure with three components:

1. **Function Calling Planner** — builds the task graph/flow;
2. **Task Fetching Unit** — dispatches ready tasks;
3. **Executor** — runs calls, including parallel calls.

Feedback can trigger replanning.

### Why this matters for decomposition research

Many decomposition papers implicitly assume a sequence.

LLMCompiler makes **dependencies and parallelism explicit**.

Therefore, a learned decomposition memory should ideally store more than an ordered list. It could store:

- nodes/subtasks,
- precedence edges,
- parallelizable groups,
- preconditions,
- success conditions,
- observed failure boundaries.

That would be structurally richer than a workflow string.

---

## 3.5 Decomposed Prompting

**Source:** ICLR 2023.  
https://openreview.net/forum?id=_nGgzQjzaRy

### Central idea

Break a complex problem into specialized subtasks and delegate each subtask to:
- another prompt,
- an LLM,
- a trained model,
- or a symbolic tool/function.

Subtasks can themselves be recursively decomposed.

### Historical importance

This paper establishes **modular decomposition**:
- different subproblems deserve different solvers;
- a decomposition graph can connect heterogeneous modules.

### Limitation for current research

The decomposition is not a learned lifelong memory that changes through task outcomes.

---

## 3.6 Least-to-Most Prompting

**Source:** ICLR 2023.  
https://arxiv.org/abs/2205.10625

### Central idea

Two stages:
1. break the problem into simpler subproblems;
2. solve them sequentially, using earlier answers to help later ones.

### Strength

Strong easy-to-hard compositional generalization.

### Limitation

No:
- persistent memory,
- executor-feedback adaptive decomposition,
- learned structural transfer reliability,
- memory consolidation.

It is therefore a useful low-complexity decomposition baseline.

---

## 3.7 Compositional Skill Routing for LLM Agents — system also named “SkillWeaver”

**Status:** arXiv 2026 preprint.  
https://arxiv.org/abs/2606.18051

> **Do not confuse this with the 2025 web-agent SkillWeaver paper.**

### Central idea

The system formulates **Compositional Skill Routing**:

1. decompose a complex query into atomic subtasks;
2. retrieve a skill for each subtask;
3. compose a dependency-aware executable plan/DAG.

The paper argues that decomposition quality is the main bottleneck.

It introduces **skill-aware iterative decomposition**, where retrieval feedback is used to revise the task split.

### Why this is very close to the current direction

This directly implements:

> decomposition → retrieval → feedback → decomposition refinement.

Therefore, a new paper cannot claim that retrieval-aware decomposition itself is unexplored.

### Remaining distinction

A stronger idea could be:
- persistent memory over *decomposition structures* themselves;
- contrastive learning from successful versus failed decompositions;
- long-term structural consolidation across tasks;
- context-dependent pattern separation between similar decompositions;
- offline replay that reorganizes the decomposition-memory graph;
- causal structural credit assigning success/failure to specific boundaries.

---

# 4. Neuroscience and human-memory papers: mechanism-level summary

## 4.1 Complementary Learning Systems (CLS)

### Representative sources

- McClelland, McNaughton & O'Reilly (1995), *Why there are complementary learning systems in the hippocampus and neocortex*  
  https://pubmed.ncbi.nlm.nih.gov/7624455/
- O'Reilly et al. review (2011/2012), *Complementary learning systems*  
  https://pubmed.ncbi.nlm.nih.gov/22141588/
- McClelland, McNaughton & Lampinen (2020), *Integration of new information in memory*  
  https://pubmed.ncbi.nlm.nih.gov/32248773/

### Biological/cognitive claim

A major computational tension exists between:
- **rapidly storing specific new episodes**, and
- **slowly learning general statistical structure without catastrophic interference**.

CLS proposes complementary systems:
- hippocampal-like fast, sparse, episodic storage;
- cortical-like slow, overlapping, integrated knowledge.

### Agent analogue

Use two stores:

**Fast episodic store**
```text
task
trajectory
result
local observations
candidate boundaries
failure location
```

**Slow structural/procedural store**
```text
task schema
decomposition graph
subtask preconditions
transfer statistics
retrieval cues
confidence/reliability
```

Do **not** immediately rewrite the global decomposition schema after one task.

### Why this could improve an agent

It directly targets:
- catastrophic procedural interference,
- overfitting to one failure,
- memory instability,
- premature generalization.

---

## 4.2 Prioritized replay — Mattar & Daw (2018)

**Source:** *Prioritized memory access explains planning and hippocampal replay*  
https://www.nature.com/articles/s41593-018-0232-z

### Main idea

The model prioritizes replay according to expected value of backing up an experience.

A simplified concept is:

\[
Priority(e) \approx Need(e) \times Gain(e)
\]

where:
- **Need** ≈ how likely/relevant this state will be for upcoming behavior;
- **Gain** ≈ how much updating from this memory could improve future decisions.

### Agent analogue

Do not consolidate memories merely because they are:
- recent,
- similar,
- successful.

Replay/consolidate a decomposition experience when:

\[
P_i = \Pr(\text{future reuse}\mid context_i)
      \times
      \Delta U(\text{updating schema from }i)
\]

This can prioritize:
- surprising failure at a common subtask boundary,
- a successful decomposition that transfers across many tasks,
- a rare exception whose omission causes large loss.

### Difference from ReMe/ReasoningBank

Those methods refine memory utility, but Mattar–Daw supplies a more explicit normative principle for **which experiences deserve offline replay/update**.

---

## 4.3 Schema-dependent rapid learning — Tse et al.

Sources:

- Tse et al. (2007), *Schemas and memory consolidation*  
  https://pubmed.ncbi.nlm.nih.gov/17412951/
- Tse et al. (2011), *Schema-dependent gene activation and memory encoding in neocortex*  
  https://pubmed.ncbi.nlm.nih.gov/21737703/

### Main idea

Once a relevant schema exists, compatible new information can be incorporated much faster.

### Agent analogue

Instead of always storing a new workflow:

```text
if new experience matches existing decomposition schema:
    update/extend schema
else:
    create a separated competing schema
```

A schema can represent:

```yaml
goal_family: booking
preconditions:
  - authenticated
macro_structure:
  - search
  - constrain
  - select
  - verify
  - commit
variants:
  payment_required:
    add: payment
  pagination_present:
    add: enumerate_pages
```

### Why useful

This creates compositional generalization:
- retain a stable high-level structure,
- bind novel task details into schema slots,
- avoid memorizing every trajectory as independent.

---

## 4.4 Event boundaries and event segmentation

Sources:

- Radvansky & Zacks (2017), *Event Boundaries in Memory and Cognition*  
  https://pmc.ncbi.nlm.nih.gov/articles/PMC5734104/
- DuBrow (2024), *Events and Boundaries*, Oxford Handbook of Human Memory.

### Main idea

Human experience is continuous, but memory is organized into discrete events. Boundaries tend to occur when the current event model becomes less predictive or context changes.

### Agent analogue

Instead of asking an LLM arbitrarily:

> “Split this trajectory into reusable steps.”

detect likely boundaries using signals such as:

\[
B_t =
\alpha \cdot PredictionError_t +
\beta \cdot GoalChange_t +
\gamma \cdot Tool/StateChange_t +
\delta \cdot DependencyShift_t
\]

High \(B_t\) implies a reusable subtask boundary.

### Why this is attractive for decomposition memory

Most current agent systems:
- generate a decomposition from text;
- or refine after failure.

Event segmentation suggests a different source of supervision:

> learn subtask boundaries from **changes in predictability and latent event state** observed across trajectories.

That is a more structural memory signal.

---

## 4.5 Pattern separation and pattern completion

Representative sources:

- Yassa & Stark (2011), *Pattern separation in the hippocampus*  
  https://pubmed.ncbi.nlm.nih.gov/21788086/
- Liu et al. (2016), systematic review of pattern separation/completion  
  https://pubmed.ncbi.nlm.nih.gov/26663362/

### Main idea

Memory needs two seemingly conflicting operations:

**Pattern separation**
- keep similar experiences distinct when confusing them would cause interference.

**Pattern completion**
- reconstruct a known memory from partial cues.

### Agent analogue

Suppose two tasks look similar:

```text
A: buy the cheapest *refundable* flight
B: buy the cheapest flight
```

A similarity-based memory system might retrieve the same workflow.

Pattern separation says the system should create distinct structural memories when a difference changes downstream action dependencies.

Possible rule:

\[
Separate(M_i,M_j)
\quad\text{if}\quad
Sim(Task_i,Task_j)\text{ is high}
\quad\land\quad
D_{causal}(G_i,G_j)\text{ is high}
\]

where \(G_i\) is the decomposition/dependency graph.

### Why it may outperform naive vector retrieval

Embedding retrieval favors surface semantic similarity.

Structural pattern separation can protect the agent from **negative transfer between superficially similar but procedurally different tasks**.

---

## 4.6 Reconsolidation

Representative sources:

- Schwabe, Nader & Pruessner (2014), review  
  https://pubmed.ncbi.nlm.nih.gov/24755493/
- Elsey, Van Ast & Kindt (2018), critical review  
  https://pubmed.ncbi.nlm.nih.gov/29792441/

### Main idea

A retrieved long-term memory can become modifiable and then restabilized.

The human reconsolidation literature is not uniformly settled; strong mechanistic claims have boundary conditions and alternative explanations.

### Safe engineering analogy

When a memory is retrieved and actually used:

```text
retrieve memory M
execute using M
observe outcome O
open M for contextual revision
compare expected vs actual outcome
edit or branch M
restabilize version M'
```

This is different from:
- append a new memory,
- globally overwrite an old memory.

### Why useful

The outcome gives *contextual evidence* about the exact retrieved memory. That enables targeted updates.

---

## 4.7 Retrieval-induced forgetting

**Source:** Murayama et al. (2014) meta-analysis  
https://pubmed.ncbi.nlm.nih.gov/25180807/

### Main idea

Repeatedly retrieving some information can reduce later accessibility of competing information. Competing explanations include inhibition and non-inhibitory blocking/competition, but the behavioral phenomenon is robust enough to motivate caution.

### Agent-design implication

Memory retrieval can create a **self-reinforcing policy bias**:

```text
retrieve workflow A
→ A is used more
→ A gains more successful evidence
→ A ranks higher
→ alternatives B/C are explored less
```

This can explain the 2026 finding that memory may improve stability but reduce search diversity in tree-based agents.

### Design implication

A memory system may need:
- diversity-preserving retrieval,
- counterfactual alternatives,
- anti-monopoly regularization,
- uncertainty-triggered exploration.

---

## 4.8 Successor representation

**Source:** Momennejad et al. (2017), *The successor representation in human reinforcement learning*  
https://www.nature.com/articles/s41562-017-0180-8

### Main idea

The successor representation stores expected future state occupancy rather than:
- only immediate cached values, or
- a complete explicit world model.

Conceptually:

\[
M(s,s') = \mathbb{E}\left[
\sum_{t=0}^{\infty}\gamma^t \mathbf{1}(S_t=s')
\mid S_0=s
\right]
\]

### Agent analogue

For decomposition, store expected **subtask successor structure**:

```text
search_product
  -> compare_candidates (0.88)
  -> inspect_constraints (0.74)

inspect_constraints
  -> request_missing_info (0.31)
  -> checkout (0.66)
```

Then a new task can be composed from transition structure rather than matching one whole workflow.

### Novelty potential

This is less directly represented in current text-based procedural-memory systems than “store a workflow” or “store a lesson”.

---

## 4.9 Prospective memory

**Source:** Rummel & Kvavilashvili (2023), *Current theories of prospective memory and new directions for theory development*  
https://www.nature.com/articles/s44159-022-00121-4

### Main idea

Prospective memory is remembering to perform an intended action when the appropriate future condition occurs.

### Agent analogue

A procedure should not just be:

```text
1. verify login
2. search
3. pay
```

It should encode trigger conditions:

```yaml
intention: verify_login
trigger: before any irreversible action

intention: request_confirmation
trigger: total_cost > budget OR policy_requires_confirmation
```

This makes memory **conditional and event-triggered**, rather than a rigid script.

---

# 5. Direct cross-paper comparison by design dimension

## 5.1 What is the memory object?

| Representation | Papers | Strength | Weakness |
|---|---|---|---|
| Raw / abstracted trajectory | Synapse | Preserves detail | Poor abstraction; expensive; fragile under changed environment |
| Reflection / lesson | Reflexion, ExpeL | Compact and general | Often weakly structured |
| Reasoning strategy | ReasoningBank | Transfers across tasks; includes failure lessons | Does not inherently encode an executable hierarchy |
| Workflow / routine | AWM | Strong reusable execution template | Can overfit one ordering/structure |
| Multi-granularity procedural script | MemP | Supports fine + abstract execution knowledge | Structural boundaries are still largely distilled rather than explicitly learned as causal objects |
| Dynamic procedural knowledge | ReMe | Strong lifecycle management | Broad; not dedicated to decomposition structure |
| Hierarchy-specific memory | LEGOMem | Different memories for planning vs execution | Does not by itself solve lifelong structural credit assignment |
| Executable skill/API | SkillWeaver 2025 | Robust, callable, testable | More domain/tool specific |
| In-trial subgoal chunk | HiAgent | Controls context length | Does not create a cross-task structural memory by itself |
| Episodic unit | EMA | Good segmentation/filtering | Not primarily procedural |

---

## 5.2 How is decomposition adapted?

| Method | Signal for refinement | Cross-task learned? | Key limitation |
|---|---|---:|---|
| Least-to-Most | Initial prompt decomposition | No | Fixed two-stage structure |
| Decomposed Prompting | Prompted recursive modularization | No | No lifecycle learning |
| ADaPT | Executor inability/failure | No | Relearns decomposition logic per task |
| AdaPlan-H | Task complexity / planning granularity | Limited / not a persistent structural memory | No explicit memory of which historical factorization transferred |
| HiAgent | Current subgoal / working-memory state | No | Mainly context compression |
| LLMCompiler | Dependency and executor feedback | No persistent decomposition memory | Designed around function orchestration |
| Skill-routing 2026 | Skill retrieval feedback | Iterative within task | Persistent skill library, but decomposition schema itself is not the main lifelong memory |
| LEGOMem | Orchestrator uses past procedural memories | Yes at planning-support level | Structural decomposition rule learning is not isolated as the central object |

---

## 5.3 How are failures used?

### Strong explicit use
- **ReasoningBank:** distills from successful and failed trajectories.
- **ReMe:** failure triggers + comparative insights.
- **Reflexion:** verbal reflection on feedback/mistakes.
- **ADaPT:** inability to execute triggers further decomposition.

### Indirect/partial use
- MemP: repository can be corrected/deprecated as experience accumulates.
- LLMCompiler: executor feedback can trigger replanning.
- SkillWeaver: failed practice informs honing/verification, but reusable successful skills dominate the library.

### Research gap

The most underdeveloped object is not “failure memory” itself.

It is:

> **structural failure attribution** — deciding whether failure was caused by a particular decomposition boundary, dependency edge, granularity choice, retrieval choice, or leaf-level execution error.

This is substantially more specific than general reflection.

---

# 6. Where the literature is already crowded

The following claims should **not** be used as the sole novelty of a new paper:

1. **“Store successful trajectories as reusable workflows.”**
   - AWM, Synapse, SkillWeaver, MemP, LEGOMem.

2. **“Learn from failed trajectories too.”**
   - Reflexion, ReasoningBank, ReMe.

3. **“Maintain and prune a dynamic procedural memory.”**
   - ReMe, MemP.

4. **“Use high-level memory for planning and low-level memory for execution.”**
   - LEGOMem, MemP.

5. **“Decompose more when execution is difficult.”**
   - ADaPT.

6. **“Adapt decomposition granularity to task complexity.”**
   - AdaPlan-H.

7. **“Use subgoals to structure long-horizon memory.”**
   - HiAgent.

8. **“Decompose, retrieve relevant skills, then compose a plan.”**
   - 2026 compositional skill-routing SkillWeaver.

9. **“Turn repeated trajectories into reusable executable APIs.”**
   - 2025 SkillWeaver.

10. **“Use more test-time experience to improve the memory bank.”**
    - ReasoningBank + MaTTS.

---

# 7. What still looks comparatively underexplored

These are not claims of absolute novelty, but they are better-supported open directions after comparing the papers above.

## 7.1 Persistent decomposition memory as a first-class object

Most memory papers store:
- lessons,
- workflows,
- scripts,
- trajectories,
- skills.

Most decomposition papers generate:
- subtask lists,
- trees,
- DAGs.

A more distinct memory object would be:

```yaml
decomposition_schema:
  task_family: ...
  context_features: ...
  boundary_rules:
    - condition: ...
      split_into: [...]
  dependency_graph: ...
  alternative_factorizations: ...
  success_statistics: ...
  transfer_statistics: ...
  failure_attribution:
    boundary_2: ...
    edge_3_5: ...
  executor_compatibility:
    model_A: ...
    model_B: ...
```

The key is that **the decomposition itself becomes learned memory**, not only a generated plan.

---

## 7.2 Pattern-separated structural memory

Current retrieval often asks:

> Which past task is semantically similar?

A more neuroscience-inspired question is:

> Which past task has the same **causal/dependency structure**, and which superficially similar tasks must be kept separate?

This could reduce negative transfer.

---

## 7.3 Event-boundary learning from trajectories

Instead of obtaining subtask boundaries only from an LLM prompt, infer them from:
- prediction error,
- abrupt state changes,
- tool regime changes,
- information bottlenecks,
- causal dependency switches,
- success/failure transitions.

This gives empirical supervision for hierarchy construction.

---

## 7.4 Structural credit assignment

After a failure, distinguish:

```text
Was the task decomposition wrong?
Was retrieval wrong?
Was the selected skill wrong?
Was the ordering/dependency wrong?
Was the leaf execution wrong?
```

Then update only the responsible memory component.

This is more precise than generic self-reflection.

---

## 7.5 Offline prioritized structural replay

Use a CLS-like fast/slow memory design.

Fast episodic storage:
- keeps raw new trajectories.

Offline consolidation:
- replays episodes selected by expected future structural utility;
- compares alternate decompositions;
- updates schemas only when sufficient evidence accumulates.

A replay score could be:

\[
Priority_i =
Need_i \times Gain_i \times Surprise_i \times StructuralUncertainty_i
\]

This is more differentiated than frequency-only or similarity-only memory updates.

---

## 7.6 Retrieval diversity and anti-lock-in

Because memory can constrain search diversity, retrieval should sometimes expose:

- the best-matching schema,
- a structurally different alternative,
- a known failure schema,
- a “no-memory” exploration branch.

This directly addresses retrieval-induced competition and the empirical memory/search-diversity tradeoff reported in recent agent work.

---

# 8. Suggested comparison template for experiments

A future paper should compare against at least these categories.

### Memory baselines
- No memory
- Raw trajectory retrieval / Synapse-style
- Reflexion
- ExpeL
- AWM
- ReasoningBank
- ReMe
- MemP
- LEGOMem where architecture permits

### Decomposition baselines
- No decomposition / ReAct
- Least-to-Most
- Decomposed Prompting
- ADaPT
- AdaPlan-H
- HiAgent
- LLMCompiler for tool/DAG settings
- 2026 compositional skill-routing SkillWeaver for skill-library settings

### Essential controlled tests

#### A. Negative transfer
Create pairs of tasks with:
- high semantic similarity,
- different dependency structure.

Measure whether memory retrieval hurts.

#### B. Structural transfer
Same dependency structure, different vocabulary/domain.

Measure whether the system retrieves the correct decomposition despite low surface similarity.

#### C. Granularity shift
Change executor capability.

A stronger executor should need fewer decomposition levels.

#### D. Distribution shift
Train memory on one family of workflows, then introduce a changed environment/tool schema.

Measure whether the memory:
- updates,
- branches,
- incorrectly overwrites,
- or continues using obsolete structure.

#### E. Memory growth
Measure:
- number of memory units,
- token/storage cost,
- retrieval latency,
- duplicate rate,
- contradiction rate.

#### F. Search diversity
Compare solution diversity with:
- no memory,
- top-1 retrieval,
- diverse retrieval,
- competing-schema retrieval.

#### G. Structural credit assignment
Inject controlled failure at:
- decomposition,
- retrieval,
- dependency,
- execution.

Test whether the system updates the correct component.

---

# 9. Short novelty map relative to the current idea

Assume the current idea is:

> Store/compact successful and failed task trajectories into reusable procedural memories; decompose new tasks; retrieve memory at task and subtask levels; adaptively refine decomposition based on direct executability and learned memory-transfer reliability; potentially store decomposition memories and contrastively learn structural rules from successful vs failed decompositions.

| Component | Closest prior work | Novelty pressure |
|---|---|---|
| Success + failure memory | ReasoningBank, ReMe, Reflexion | **Very high overlap** |
| Reusable procedural memory | MemP, ReMe, AWM, LEGOMem | **Very high overlap** |
| Task-level + subtask-level memory | LEGOMem, MemP | **High overlap** |
| Decompose when not executable | ADaPT | **Very high overlap** |
| Adaptive hierarchy/granularity | AdaPlan-H, HiAgent | **High overlap** |
| Retrieve skills after decomposition | 2026 compositional skill routing | **Very high overlap** |
| Store executable skills | SkillWeaver 2025 | **High overlap** |
| Store decomposition structure as a persistent first-class memory | Closest: LEGOMem/AWM + decomposition papers | **Potential gap**, but must be demonstrated carefully |
| Learn structural boundaries from trajectory prediction/error signals | Neuroscience-inspired event segmentation; less explicit in searched agent work | **Promising gap** |
| Pattern-separate similar tasks by causal/dependency structure | Pattern-separation inspiration; not central in searched procedural-memory agents | **Promising gap** |
| Assign credit specifically to boundaries/edges/granularity decisions | MemPO provides memory credit-assignment inspiration, but structural credit is more specific | **Promising gap** |
| Prioritized offline replay of decomposition experiences | Mattar–Daw + CLS inspiration; not central in compared agent methods | **Promising gap** |
| Preserve alternative decompositions to avoid retrieval lock-in | Motivated by retrieval-induced forgetting + recent memory/search tradeoff | **Promising gap** |

---

# 10. Most important takeaways

### Takeaway 1 — Memory alone is no longer a sufficient novelty axis

The 2023–2026 literature already covers:
- reflections,
- trajectory exemplars,
- experiential insights,
- workflows,
- procedural scripts,
- multi-level memories,
- dynamic memory pruning,
- failure-aware reasoning memory,
- executable skills.

### Takeaway 2 — Adaptive decomposition is also crowded

The literature already covers:
- recursive decomposition,
- executability-triggered refinement,
- coarse-to-fine hierarchy,
- working-memory subgoals,
- dependency-aware DAGs,
- skill-aware iterative decomposition.

### Takeaway 3 — The better open question is *structural learning*

The most promising distinction is not:

> “Can the agent remember a solution?”

but:

> “Can the agent learn a reusable model of **how task structure should be factorized**, when a factorization is valid, when it should be separated from a similar schema, and which structural decision caused success or failure?”

### Takeaway 4 — Neuroscience is most useful when it supplies a computational principle

The strongest mechanisms are:

- **CLS:** fast episodes + slow consolidated structure;
- **prioritized replay:** update memories according to future decision value;
- **schema learning:** rapidly integrate compatible information;
- **event segmentation:** infer boundaries from predictability changes;
- **pattern separation/completion:** separate conflicting similar structures while completing known ones from partial cues;
- **reconsolidation:** contextually edit a retrieved memory;
- **retrieval competition:** avoid one memory suppressing all alternatives;
- **successor representation:** encode reusable transition structure;
- **prospective memory:** attach procedures to trigger conditions.

These are more useful than simply saying a system is “brain-inspired”.

---

# 11. Primary references

## Agent memory and procedural learning

1. Ouyang et al. **ReasoningBank: Scaling Agent Self-Evolving with Reasoning Memory.** ICLR 2026.  
   https://openreview.net/forum?id=jL7fwchScm

2. Cao et al. **Remember Me, Refine Me: A Dynamic Procedural Memory Framework for Experience-Driven Agent Evolution.** Findings ACL 2026.  
   https://aclanthology.org/2026.findings-acl.829/

3. Fang et al. **Memp: Exploring Agent Procedural Memory.** Findings ACL 2026.  
   https://aclanthology.org/2026.findings-acl.866/

4. Han et al. **LEGOMem: Modular Procedural Memory for Multi-agent LLM Systems for Workflow Automation.** AAMAS 2026.  
   https://doi.org/10.65109/VLUA1303

5. Wang et al. **Agent Workflow Memory.** ICML 2025.  
   https://proceedings.mlr.press/v267/wang25bx.html

6. Zhao et al. **ExpeL: LLM Agents Are Experiential Learners.** AAAI 2024.  
   https://doi.org/10.1609/aaai.v38i17.29936

7. Zheng et al. **Synapse: Trajectory-as-Exemplar Prompting with Memory for Computer Control.** ICLR 2024.  
   https://proceedings.iclr.cc/paper_files/paper/2024/hash/52f050499cf82fa8efb588e263f6f3a7-Abstract-Conference.html

8. Shinn et al. **Reflexion: Language Agents with Verbal Reinforcement Learning.** NeurIPS 2023.  
   https://proceedings.neurips.cc/paper_files/paper/2023/hash/1b44b878bb782e6954cd888628510e90-Abstract-Conference.html

9. Dai et al. **RecMem: Recurrence-based Memory Consolidation for Efficient and Effective Long-Running LLM Agents.** Findings ACL 2026.  
   https://aclanthology.org/2026.findings-acl.1619/

10. Li et al. **MemPO: Self-Memory Policy Optimization for Long-Horizon Agents.** Findings ACL 2026.  
    https://aclanthology.org/2026.findings-acl.1166/

11. Lan et al. **EMA: An Episodic Memory Agent for Efficient and Selective Memory.** Findings ACL 2026.  
    https://aclanthology.org/2026.findings-acl.250/

12. Zheng et al. **SkillWeaver: Web Agents can Self-Improve by Discovering and Honing Skills.** arXiv, 2025.  
    https://arxiv.org/abs/2504.07079

13. Zhao et al. **Demystify the Role of Memory in Machine Learning Engineering Agents.** Findings ACL 2026.  
    https://aclanthology.org/2026.findings-acl.525/

## Decomposition and hierarchical planning

14. Prasad et al. **ADaPT: As-Needed Decomposition and Planning with Language Models.** Findings NAACL 2024.  
    https://aclanthology.org/2024.findings-naacl.264/

15. Tan et al. **From Coarse to Fine: Self-Adaptive Hierarchical Planning for LLM Agents (AdaPlan-H).** Findings ACL 2026.  
    https://aclanthology.org/2026.findings-acl.77/

16. Hu et al. **HiAgent: Hierarchical Working Memory Management for Solving Long-Horizon Agent Tasks with Large Language Model.** ACL 2025.  
    https://aclanthology.org/2025.acl-long.1575/

17. Kim et al. **An LLM Compiler for Parallel Function Calling.** ICML 2024.  
    https://proceedings.mlr.press/v235/kim24y.html

18. Khot et al. **Decomposed Prompting: A Modular Approach for Solving Complex Tasks.** ICLR 2023.  
    https://openreview.net/forum?id=_nGgzQjzaRy

19. Zhou et al. **Least-to-Most Prompting Enables Complex Reasoning in Large Language Models.** ICLR 2023.  
    https://arxiv.org/abs/2205.10625

20. Gao. **Compositional Skill Routing for LLM Agents: Decompose, Retrieve, and Compose.** arXiv, 2026.  
    https://arxiv.org/abs/2606.18051

## Neuroscience / cognitive science

21. McClelland, McNaughton & O'Reilly. **Why there are complementary learning systems in the hippocampus and neocortex.** Psychological Review, 1995.  
    https://pubmed.ncbi.nlm.nih.gov/7624455/

22. O'Reilly et al. **Complementary learning systems.** Cognitive Science, 2011/2012.  
    https://pubmed.ncbi.nlm.nih.gov/22141588/

23. McClelland, McNaughton & Lampinen. **Integration of new information in memory: new insights from a complementary learning systems perspective.** 2020.  
    https://pubmed.ncbi.nlm.nih.gov/32248773/

24. Mattar & Daw. **Prioritized memory access explains planning and hippocampal replay.** Nature Neuroscience, 2018.  
    https://www.nature.com/articles/s41593-018-0232-z

25. Tse et al. **Schemas and memory consolidation.** Science, 2007.  
    https://pubmed.ncbi.nlm.nih.gov/17412951/

26. Tse et al. **Schema-dependent gene activation and memory encoding in neocortex.** Science, 2011.  
    https://pubmed.ncbi.nlm.nih.gov/21737703/

27. Radvansky & Zacks. **Event Boundaries in Memory and Cognition.** Current Opinion in Behavioral Sciences, 2017.  
    https://pmc.ncbi.nlm.nih.gov/articles/PMC5734104/

28. Yassa & Stark. **Pattern separation in the hippocampus.** Trends in Neurosciences, 2011.  
    https://pubmed.ncbi.nlm.nih.gov/21788086/

29. Liu et al. **Tests of pattern separation and pattern completion in humans—A systematic review.** Hippocampus, 2016.  
    https://pubmed.ncbi.nlm.nih.gov/26663362/

30. Schwabe, Nader & Pruessner. **Reconsolidation of human memory: brain mechanisms and clinical relevance.** Biological Psychiatry, 2014.  
    https://pubmed.ncbi.nlm.nih.gov/24755493/

31. Elsey, Van Ast & Kindt. **Human memory reconsolidation: A guiding framework and critical review of the evidence.** Psychological Bulletin, 2018.  
    https://pubmed.ncbi.nlm.nih.gov/29792441/

32. Murayama et al. **Forgetting as a consequence of retrieval: a meta-analytic review of retrieval-induced forgetting.** Psychological Bulletin, 2014.  
    https://pubmed.ncbi.nlm.nih.gov/25180807/

33. Momennejad et al. **The successor representation in human reinforcement learning.** Nature Human Behaviour, 2017.  
    https://www.nature.com/articles/s41562-017-0180-8

34. Rummel & Kvavilashvili. **Current theories of prospective memory and new directions for theory development.** Nature Reviews Psychology, 2023.  
    https://www.nature.com/articles/s44159-022-00121-4

---

## 12. Final synthesis in one diagram

```text
                       ┌──────────────────────┐
                       │  New task / context  │
                       └──────────┬───────────┘
                                  │
                         retrieve candidate
                       structural/procedural
                              memories
                                  │
               ┌──────────────────┴───────────────────┐
               │                                      │
       surface/semantic match                 structural match
      (common current systems)          (causal/dependency schema)
               │                                      │
               └──────────────────┬───────────────────┘
                                  │
                     candidate decomposition
                                  │
                     ┌────────────┴────────────┐
                     │                         │
                executable?               uncertain /
                     │                     interference
             yes ────┘                         │
                     │                  retrieve alternatives
                     │                  / separate patterns
                     ▼                         │
                  execute ◄────────────────────┘
                     │
                  outcome
                     │
          ┌──────────┴──────────┐
          │                     │
   leaf execution error   structural/decomposition error
          │                     │
    update skill          update boundary/edge/schema
          │                     │
          └──────────┬──────────┘
                     │
             fast episodic store
                     │
         prioritized offline replay
            Need × Gain × Surprise
                     │
                     ▼
           slow consolidated schema
```

**Core research opportunity identified by the comparison:** move from **memory of solutions** to **memory of task structure**, with explicit boundary learning, pattern separation, structural credit assignment, and prioritized consolidation.
