# ReasoningBank: official provenance and static source audit

Recorded 2026-09-16 during cycle 15, without changing its frozen protocol or
source collector. Branch `codex/copromem-research-loop`, unchanged project HEAD
`18025102c010e85f26b0b3fb1144a1cb684b587e`. No commit, push or vendor edits.

## Verified source and scope

The [Google Research author blog](https://research.google/blog/reasoningbank-enabling-agents-to-learn-from-experience/)
links to [google-research/reasoning-bank](https://github.com/google-research/reasoning-bank).
This resolves earlier official-code uncertainty; a similarly named third-party
repository must not substitute for this provenance.

Fresh, detached, clean checkout:
`artifacts/research/baseline_sources/reasoning-bank`, commit
`ed80611788292ea739f1effd31f16c53823b8a0d`. All 97 Python files passed syntax
parsing. Selected source hashes and the verification timestamp are archived in
`artifacts/research/reasoningbank_audit_20260916/source_audits/9501cdc050e28d22ac33d3ff4d454a979a56bfa4259698614f2cd6f370ef3009.json`.

Inspected README, dependency metadata, WebArena memory management/induction and
the mini-swe-agent memory implementation. No benchmark task JSON contents,
held-out tasks or trajectories were opened. No dependency installation, module
initialization, embedding download, provider call or policy rollout was performed
for this static audit. Syntax success is not runtime reproduction.

## Implementation observations, not measured benchmark effects

- The root metadata requires Python >=3.13 and pins BrowserGym packages to
  0.14.1, while many other dependencies have lower bounds rather than a complete
  environment lock. README instructs installation from root `requirements.txt`,
  but that file is absent at the pinned revision. This is an entry-point mismatch,
  not evidence that the project cannot be installed through its actual metadata.
- Importing WebArena's memory module initializes Vertex AI and a Google GenAI
  client. Its native cloud configuration is not supplied by our OpenRouter key.
  Do not silently change credentials/backend and call the result exact reproduction.
- `screening` loads the existing embedding cache, embeds and appends the current
  query, then ranks against the previously loaded cache. The just-appended entry
  therefore cannot retrieve itself in that same call. Previously cached repeated
  task IDs are not explicitly excluded by this function. This is a static
  contamination risk requiring split-aware fixtures, not an observed benchmark leak.
- With a nonempty cache, ranking uses an instruction-conditioned Gemini embedding
  even when the initial query embedding uses the Qwen option. Thus Qwen selection
  is not a fully local fallback. An empty cache returns after appending the query
  and before this second embedding call. Mixing dimensions/backends also requires
  validation; the code does not by itself establish comparable embedding spaces.
- `select_memory` truncates ranked IDs before finding the first matching bank
  item by `task_id`. Cache IDs without corresponding bank entries can consume
  top-n slots. Duplicate IDs and identity types require explicit lifecycle tests.
  Cache writes and memory-bank admission are separate state transitions.
- Induction offers native-reward (`gt`) and model-evaluated (`autoeval`) outcome
  modes; available auto-evaluation explanation text can enter the induction
  trajectory. Feedback privilege and generation costs must be matched explicitly.
- README documents vendored WebArena annotation, evaluator and action-execution
  patches. The canonical scorer/environment must be validated and shared across
  all comparison arms, not silently changed only for ReasoningBank or CoProCon.

Source references are the unchanged files in the pinned checkout, principally
`WebArena/memory_management.py`, `WebArena/induce_memory.py`, `README.md` and
`pyproject.toml`. These observations describe this implementation revision;
they are not blanket claims about every ReasoningBank implementation or paper.

## Decision and next gates

**KEEP** ReasoningBank on the six-method priority shortlist and retain this
official source. Status: **official provenance and static-code audit only**.
No published score, native retrieval quality or end-to-end policy result has
been reproduced. Its textual memory remains a strong competing explanation for
any claimed value of contrast-derived executable memory.

Next gates: isolated installation with an explicit resolved environment;
source-bound cache/bank lifecycle fixtures; real embedding configuration and
cost verification; native induction/policy smoke tests; then a documented common
adapter with identical task splits, feedback, evaluator and resource accounting.
An offline fixture with synthetic embeddings can check code behavior but must
not be described as embedding-model or full ReasoningBank reproduction.

## Follow-up: isolated source-function cache fixtures

Later on 2026-09-16, ten authored behavioral checks passed on two independent
container runs with identical structured outputs. The fixture compiles only five
reviewed, hash-pinned function definitions from the unchanged upstream file.
It deliberately bypasses module initialization and substitutes deterministic
three-dimensional embedding functions. Actual tensor operations use the existing
isolated ExpeL image (Python 3.9.17, torch 2.0.1+cpu), **not** ReasoningBank's
declared Python/dependency environment. No cloud client, actual embedding model,
benchmark data, native agent policy or paid call is involved.

Observed fixture behavior: missing-cache creation and append; same-call exclusion
of the fresh entry; possible later same-task retrieval; stale top-ID slot loss;
duplicate-ID repetition of the first bank match; integer/string identity mismatch;
non-enforcement of the logged n<=10 warning; one embedding call for an empty Qwen
cache; Qwen plus Gemini calls for a nonempty cache; and a synthetic mixed-dimension
append that makes the next cache load fail. These are exact results for constructed
inputs, **not measured production contamination, retrieval accuracy or dimension
failures with the real model checkpoints**.

The first launch failed because the reused image already has a Python entry point;
the launcher duplicated `python`. Its raw failed record remains. Correcting only
the launcher gave two passing repeats. Moving a lint suppression comment then
produced two more passing repeats with the same outputs, all retained. No vendor
or frozen AppWorld collector source changed.

- Runner: `research/scripts/probe_reasoningbank_cache.py`.
- Fixture: `research/fixtures/reasoningbank_cache_lifecycle.py`.
- Final source/runner/image binding:
  `8156e953cb8a1607fb93d3bea4684df69b8c7797aec1350dedbee16625b21cac`.
- Final repeat audit:
  `artifacts/research/reasoningbank_audit_20260916/cache_fixture_audits/a29ad31c21f5288e46caf16014143890c864dbf828ec54894068992f1e806996.json`.
- Failed launch: `cache_fixture_runs/8f5d76bca1d8411f98b9f747f608f64bd47bece2c58de02f385ba3930bc9ff93.json`.

**KEEP** these source-behavior fixtures as adaptation checks. They strengthen the
case for explicit bank/cache identity, split and resource accounting. Status is
now **static audit plus source-function fixtures**; full/native reproduction is
still absent. No upstream quirk is silently repaired or used to weaken a baseline.
