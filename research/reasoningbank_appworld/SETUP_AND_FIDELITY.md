# ReasoningBank baseline on AppWorld

## Scope

The official ReasoningBank release supports WebArena and SWE-Bench, not
AppWorld.  This package is therefore an **adapted ReasoningBank baseline on
AppWorld**, not a reproduction of the paper's WebArena numbers.

Pinned upstream:

- repository: `https://github.com/google-research/reasoning-bank`
- commit: `ed80611788292ea739f1effd31f16c53823b8a0d`
- paper: arXiv:2509.25140v2
- license: Apache-2.0

## Preserved ReasoningBank semantics

- memory is induced from both self-judged successful and failed trajectories;
- judge temperature is 0.0;
- extraction temperature is 1.0 and uses the upstream success/failure prompts;
- each experience stores task query, trajectory identity, proxy outcome and
  structured memory text;
- retrieval is cosine search over task-query embeddings with `k=1`;
- retrieved items are accompanied by the upstream memory-use instruction;
- consolidation is append-only with no pruning;
- dynamic evaluation is streaming: retrieve, execute, self-judge, extract,
  then append before the next task.

## AppWorld comparison controls

For a scientific comparison against CoProMem, every arm must share:

- the same AppWorld split, task order, seeds and official scorer;
- the same AppWorld executor and prompt/tool interface;
- the same backbone model route, temperature 0.7, context/output ceilings and
  maximum actions;
- the same acquisition/evaluation exposure policy;
- independent memory state and complete retrieval/update provenance;
- identical retry, truncation, storage, ledger and terminal-reconciliation
  policy.

AppWorld's official score is used for analysis only.  It must not label
ReasoningBank memories because the paper uses an LLM self-judge at test time.

## Explicit deviations from the paper

1. The benchmark and action space are AppWorld rather than BrowserGym/WebArena.
2. The shared AppWorld agent prompt slot wraps the ReasoningBank instruction;
   this boundary must be hash-audited in a fixture before paid execution.
3. If the comparison uses the existing DeepSeek executor, then the agent,
   judge and extractor backbone differs from the paper's Gemini/Claude tables.
4. Any non-Gemini embedding route is a retrieval-model deviation and must be
   named in the manifest.  The primary fidelity profile should use
   `gemini-embedding-001` if Vertex credentials are available.
5. A warm-start bank built from shared acquisition trajectories is a study
   design choice, not the paper's empty-bank streaming setup.  Report it as a
   separate arm/profile.

## Recommended staged run

Do not add ReasoningBank directly to the 540-trajectory confirmatory run.

1. Zero-provider tests and upstream parity check.
2. Local deterministic fixture covering success and failure induction,
   top-1 retrieval, empty-bank behavior, fixed immutability, dynamic append,
   crash/restart and byte-identical offline reproduction.
3. Six-trajectory engineering run: two tasks, ReasoningBank and No Memory,
   three trials.  This validates prompt visibility and online updates only.
4. Thirty-task paired exploratory baseline after engineering passes.
5. A new preregistered confirmatory study only after the baseline is frozen.

## Zero-provider setup

```powershell
git clone https://github.com/google-research/reasoning-bank.git E:\Project\AAMAS\reasoning-bank-upstream-ed80611
git -C E:\Project\AAMAS\reasoning-bank-upstream-ed80611 checkout --detach ed80611788292ea739f1effd31f16c53823b8a0d

python scripts/prepare_reasoningbank_appworld.py `
  --upstream-checkout E:\Project\AAMAS\reasoning-bank-upstream-ed80611 `
  --output artifacts\zero-cost-validation\reasoningbank-appworld-preflight.json

python -m pytest -q tests/reasoning_bank
```

These commands do not open AppWorld task payloads or make provider calls.

