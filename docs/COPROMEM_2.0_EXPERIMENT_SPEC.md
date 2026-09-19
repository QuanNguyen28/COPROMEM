# COPROMEM 2.0: Experimental Design, Benchmark Justification & OpenRouter Protocol

**Version:** 19 September 2026
**Scope:** Authoritative specification for evaluating COPROMEM 2.0 against SOTA memory and decomposition methods, establishing benchmark justifications, mapping canonical literature models, and executing reproducible runs via the OpenRouter API.

---

## 1. Executive Summary & Core Hypothesis

COPROMEM 2.0 posits that an agent improves lifelong performance not by memorizing solution texts (*Memory of Solutions*), but by accumulating and refining **Task Decomposition Schemas** with explicit handoff invariants, causal pattern separation, and 4-tier failure credit assignment (*Memory of Task Structure*).

### Core Falsifiable Hypotheses

* **H1 (Zero Harmful Flips under Causal Deception):** When presented with *Deceptive Twin-Tasks* (surface semantic similarity $S_{\text{semantic}} \ge 0.40$ but causal graph conflict $D_{\text{causal}} \ge 0.35$), COPROMEM 2.0 triggers Pattern Separation, driving harmful transfer flips to zero ($\text{Harmful Flips} = 0$), whereas standard Semantic RAG experiences substantial negative transfer ($\text{Harmful Flips} > 0$).
* **H2 (Handoff Invariant Efficiency):** In multi-step, stateful multi-agent tasks (AppWorld-style), enforcing verified executable contracts at role interfaces yields higher task success with fewer total rollouts than unconstrained re-planning or unstructured verbal reflection.
* **H3 (Structural Credit Precision):** Upon task failure, 4-Tier Structural Credit Assignment correctly pinpoints the failure locus (Handoff, Dependency, Scope, or Leaf) with $\ge 90\%$ accuracy, preventing erroneous mutations of global decomposition schemas when only leaf execution failed.
* **H4 (CLS Stability & Anti-Lock-in):** Mattar–Daw prioritized offline replay maintains long-term memory stability (preventing catastrophic interference) while diverse schema retrieval preserves search exploration under distribution shifts.

---

## 2. Benchmark Justification: Why Other Benchmarks Fail

A rigorous paper must justify why standard LLM benchmarks are inadequate for evaluating procedural coordination memory:

```text
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                           BENCHMARK SUITABILITY MATRIX                                  │
├──────────────────────┬─────────────┬──────────────┬───────────────┬─────────────────────┤
│ Benchmark            │ Multi-Agent │ Stateful Env │ Graph (DAG)   │ Diagnostic Utility  │
│                      │ Handoffs?   │ Side-Effects?│ Dependencies? │ for COPROMEM 2.0    │
├──────────────────────┼─────────────┼──────────────┼───────────────┼─────────────────────┤
│ GSM8K / MATH         │ ❌ No        │ ❌ No         │ ❌ Linear Seq │ 🔴 Poor (Confounded)│
│ HumanEval / MBPP     │ ❌ No        │ ❌ No         │ ❌ Single-Turn│ 🔴 None             │
│ HotpotQA / 2Wiki     │ ❌ No        │ ❌ No         │ ❌ Linear RAG │ 🔴 None (Passive)   │
│ ALFWorld             │ ⚠️ Minimal   │ ⚠️ Shallow    │ ❌ Linear Chain│ 🟡 Weak             │
│ ToolBench / RestBench│ ⚠️ Modular   │ ⚠️ API Calls  │ ✅ Rich DAG   │ 🟢 High             │
│ AppWorld             │ ✅ Full      │ ✅ 9 Real Apps│ ✅ Complex DAG│ 🟢 Gold Standard    │
│ Synthetic Twin-Task  │ ✅ Controlled│ ✅ Explicit   │ ✅ Formal DAG │ 🟢 Pure Ground-Truth│
└──────────────────────┴─────────────┴──────────────┴───────────────┴─────────────────────┘
```

### In-Depth Critique of Common Benchmarks

1. **The Arithmetic Fallacy of GSM8K / MATH:**
   * In GSM8K, the agent's failure mode is dominated by arithmetic calculation errors (e.g. $14 \times 13 = 172$).
   * As proven in our repository's cycle audits (`research/008_PIVOT_RESEARCH_SPECIFICATION.md`), multiple success/failure pairs using Gemma models produced **identical high-level planner artifacts**. The downstream error came from arithmetic stochasticity, completely confounding whether memory helped coordination.
2. **The Single-Turn Trap of HumanEval / MBPP:**
   * Evaluates single-function synthesis against unit tests. There is no intermediate handoff between specialized roles, no persistent execution state, and no multi-episode transfer.
3. **The Passive Text Limitation of HotpotQA:**
   * Multi-hop QA is an information retrieval task with no environmental side-effects. The agent never changes state, meaning there are no postconditions or invariant violations to enforce.
4. **The Linear Simplicity of ALFWorld:**
   * Text games follow rigid sequential action chains ($A \to B \to C$). They lack branching DAG structures, parallel execution waves, and causal deception.

### The Chosen Benchmark Suite

* **Tier 1 (Clean Mathematical Ground-Truth): Extended Synthetic Twin-Task Benchmark:**
  * Fully deterministic, zero financial cost, zero stochastic API noise.
  * Allows exact paired counterfactual execution with identical seed draws.
  * Provides rigorous mathematical proofs for Negative Transfer elimination and Fault Injection attribution.
* **Tier 2 (Real-World Stateful Multi-Agent Environment): AppWorld & Multi-App Slice:**
  * 9 digital applications (Gmail, Calendar, Amazon, Venmo, Messenger, Notes, Phone, Clock, Contacts) interacting over 457 APIs backed by a stateful SQLite database.
  * Natural multi-agent roles: Planner $\to$ API Dispatcher $\to$ Executor $\to$ Verifier.
  * Rich invariant violations: e.g., missing API arguments, unauthorized transactions, overdraft conditions, and uncommitted database changes.

---

## 3. Canonical Literature Model Alignment

To eliminate the enormous computational and financial cost of re-running competing baseline systems (ReasoningBank, ReMe, AWM, AppWorld), we align our OpenRouter evaluation directly with the **exact canonical backbone models** used in their published papers:

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        CANONICAL LITERATURE BACKBONE MAPPING                           │
├────────────────────┬─────────────────────────────┬─────────────────────────────────────┤
│ Published Method   │ Literature Backbone Model   │ Pinned OpenRouter Endpoint          │
├────────────────────┼─────────────────────────────┼─────────────────────────────────────┤
│ ReasoningBank      │ gpt-4o-mini                 │ openai/gpt-4o-mini                  │
│ (ICLR 2026)        │ llama-3.1-70b-instruct      │ meta-llama/llama-3.3-70b-instruct   │
├────────────────────┼─────────────────────────────┼─────────────────────────────────────┤
│ ReMe               │ gpt-4o                      │ openai/gpt-4o                       │
│ (ACL 2026)         │ llama-3-70b-instruct        │ meta-llama/llama-3.3-70b-instruct   │
├────────────────────┼─────────────────────────────┼─────────────────────────────────────┤
│ AppWorld           │ claude-3-5-sonnet           │ anthropic/claude-3.5-sonnet         │
│ (ACL/NeurIPS 2024) │ gpt-4o / llama-3-70b        │ openai/gpt-4o-mini & llama-3.3-70b  │
├────────────────────┼─────────────────────────────┼─────────────────────────────────────┤
│ AWM                │ gpt-4-turbo / gpt-3.5-turbo │ openai/gpt-4o-mini (modern equiv)   │
│ (ICML 2025)        │                             │                                     │
└────────────────────┴─────────────────────────────┴─────────────────────────────────────┘
```

### Strategic Advantage for Publication

By evaluating COPROMEM 2.0 on OpenRouter with `openai/gpt-4o-mini` and `meta-llama/llama-3.3-70b-instruct`:

1. We directly compare against the published baseline figures of ReasoningBank, ReMe, and AWM.
2. We evaluate our method under identical compute budgets without spending thousands of dollars re-running unverified legacy vendor code.
3. Reviewers receive an apples-to-apples comparison on canonical model backbones.

---

## 4. The Controlled Twin-Task Protocol (Causal Deception Test)

### Mathematical Formulation of Twin-Tasks

Let $T_A$ and $T_B$ be a pair of tasks characterized by semantic tokens $\mathcal{W}$ and causal dependency DAGs $\mathcal{G} = (\mathcal{V}, \mathcal{E})$:

$$
\text{Sim}_{\text{semantic}}(T_A, T_B) = \frac{|\mathcal{W}_A \cap \mathcal{W}_B|}{|\mathcal{W}_A \cup \mathcal{W}_B|} \ge \tau_{\text{semantic}} \quad (\text{default: } 0.40)
$$

$$
D_{\text{causal}}(T_A, T_B) = 0.3 \cdot D_{\text{roles}} + 0.5 \cdot D_{\text{edges}} + 0.2 \cdot D_{\text{preconditions}} \ge \tau_{\text{causal}} \quad (\text{default: } 0.35)
$$

### Four Counterfactual Evaluation Arms

Each task is evaluated across four matched arms on identical starting checkpoints:

1. **Arm 1 (No Memory / ReAct):** The agent generates a new decomposition plan on the fly with zero cross-task memory.
2. **Arm 2 (Semantic RAG):** Retrieves the highest cosine-similarity prior trajectory based purely on embedding overlap:

   $$
   \text{Retrieve}(T) = \arg\max_M \text{Sim}_{\text{semantic}}(T, M)
   $$

   *Failure Mode:* Retrieves $T_A$'s workflow for $T_B$, causing negative transfer.
3. **Arm 3 (COPROMEM-v1 / CoProCon):** Executes a static procedural verifier at handoff without pattern separation or DAG schema learning.
4. **Arm 4 (COPROMEM 2.0 - Proposed):**

   * Computes $D_{\text{causal}}$ alongside $S_{\text{semantic}}$.
   * Triggers Pattern Separation if $S_{\text{semantic}} \ge 0.40$ and $D_{\text{causal}} \ge 0.35$.
   * Enforces verified Handoff Contracts at graph edges.
   * Diagnoses failures using 4-Tier Structural Credit Assignment.
   * Consolidates episodic traces into persistent schemas via Mattar–Daw prioritized offline replay.

### Key Metrics

* **Beneficial Flips ($G$):** Baseline fails $\to$ Arm passes.
* **Harmful Flips ($H$):** Baseline passes $\to$ Arm fails (Negative Transfer).
* **Net Improvement ($\Delta$):** $G - H$.
* **Attribution Accuracy:** Accuracy of localizing injected structural faults across Tiers 1–4.
* **Cost Efficiency:** Token proxy and USD cost per successful completion.

---

## 5. OpenRouter Multi-Agent Harness Architecture

### Pre-Reservation & Settlement Budget Ledger

To ensure zero financial runaway, all HTTP interactions go through `BudgetedOpenRouterClient`:

```text
               ┌──────────────────────────────────────────────┐
               │              Target Request                  │
               │   Model: openai/gpt-4o-mini                  │
               │   Max Tokens: 1,000                          │
               └──────────────────────┬───────────────────────┘
                                      │
                                      ▼
               ┌──────────────────────────────────────────────┐
               │         1. BudgetLedger.reserve(bound)       │
               │   Calculate upper-bound cost:                │
               │   bound = max_tokens * price_per_token       │
               │   Check: total_reserved + bound <= max_usd   │
               └──────────────────────┬───────────────────────┘
                                      │ Success
                                      ▼
               ┌──────────────────────────────────────────────┐
               │    2. Execute HTTP Call to OpenRouter API    │
               │    Endpoint: /api/v1/chat/completions        │
               └──────────────────────┬───────────────────────┘
                                      │ Response received
                                      ▼
               ┌──────────────────────────────────────────────┐
               │         3. BudgetLedger.settle(key, actual)  │
               │   Extract actual prompt & completion tokens  │
               │   Refund the unused reservation difference   │
               └──────────────────────────────────────────────┘
```

### Prompt Engineering & Structured JSON Invariants

All role interactions are strictly bound to JSON schemas:

#### Planner System Prompt Template:

```text
You are the Lead Task Planner in a multi-agent workflow.
Decompose the user's objective into a structured Dependency DAG.
Output ONLY valid JSON adhering to the following schema:
{
  "task_family": string,
  "nodes": [{"node_id": string, "role": string, "intent": string, "input_keys": string[], "output_keys": string[]}],
  "edges": [{"source_node": string, "target_node": string, "contract_id": string}],
  "preconditions": string[],
  "declared_invariants": Record<string, any>
}
```

#### Handoff Verifier Prompt Template:

```text
You are the Handoff Contract Auditor at interface {interface}.
Contract: {contract_id}
Precondition: {precondition}
Invariant: {postcondition}
Examine the producer's artifact:
{artifact}
Verify whether all invariants hold. If violated, state the exact missing field and recovery instruction.
```

---

## 6. Execution Command-Line Interface (CLI)

The harness is executable via `copromem-openrouter-pilot` or python module invocation:

```bash
# Set your OpenRouter API key
export OPENROUTER_API_KEY="sk-or-v1-..."

# Run the live multi-agent pilot on canonical gpt-4o-mini
conda run -n copromem python -m copromem.openrouter_experiment \
  --model openai/gpt-4o-mini \
  --max-usd 0.50 \
  --max-calls 20 \
  --seed 42 \
  --output artifacts/openrouter_pilot_gpt4o_mini.json

# Run on open-weights llama-3.3-70b
conda run -n copromem python -m copromem.openrouter_experiment \
  --model meta-llama/llama-3.3-70b-instruct \
  --max-usd 0.50 \
  --max-calls 20 \
  --seed 42 \
  --output artifacts/openrouter_pilot_llama70b.json
```

All run traces, token accounting, and flip comparisons are automatically saved into structured JSON reports with full reproducibility guarantees.
