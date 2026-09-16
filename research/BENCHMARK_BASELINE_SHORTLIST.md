# Evaluation shortlist and reproduction status — 16 September 2026

## Research baselines

Shortlist six research baselines, in addition to the mandatory no-memory, success-only,
textual-rule, static-verifier and equal-compute controls. This separates literature breadth
from causal controls; a large arm count does not replace a fair intervention comparison.

| Baseline | Why include it | Current local status | Required reproduction evidence |
|---|---|---|---|
| ExpeL | Experience-derived textual rules | Historical GSM8K prompt adaptation only; one saved null-induction result excluded | Official pinned code, valid induction, original-task smoke, adaptation diff |
| AWM | Success-derived workflow memory | Historical offline prompt adaptation | Confirm workflow extraction/retrieval fidelity and native executor compatibility |
| ReasoningBank | Success/failure strategies and memory scaling | Primary paper inspected; no implementation integrated | Verify official code provenance; freeze memory extraction, retrieval and compute budget |
| CONTRAMEM | Closest same-task contrast memory | Primary method inspected; official code availability unverified | Author release or explicitly labelled paper-based implementation; matched source trajectories |
| Skill-Pro | Learned reusable skills with validation gate | Primary v3 paper and linked repository located | Verify actual gate implementation, dependency environment and ability to match our executor |
| AgentSpec | Strong executable-rule enforcement comparison | Primary paper and official repository located | Same rule language, observations and recovery interface; separate manual and generated rules |

[CRITIC](https://arxiv.org/abs/2305.11738) remains an additional recovery/tool-feedback control;
the repository's existing arithmetic adapter is not an exact reproduction. [ASI](https://arxiv.org/abs/2504.06821)
is a reserve baseline if the method pivots toward reusable executable skills.

Official sources and overlap details are linked in `NOVELTY_MATRIX_20260916.md`.

## Four benchmark families

| Family / benchmark | Procedural signal and observable handoff | Outcome scoring | Adapter cost / current status |
|---|---|---|---|
| Stateful API workflows: [AppWorld](https://github.com/StonyBrookNLP/appworld) | Planner to code/tool actor; API arguments and database state changes | Programmatic goal and collateral-change tests | Strong fit, medium/high setup. Only train/dev development. No adapter installed or validated yet. |
| Browser enterprise workflows: [WorkArena++](https://github.com/ServiceNow/WorkArena) | Task decomposition to browser action; forms, records and workflow state | Native task validation | Strong repeated procedures; browser/service setup and reproducible state snapshots are substantial work. |
| Repository repair: [SWE-bench](https://github.com/SWE-bench/SWE-bench) | Diagnosis to patch to test runner | Native isolated repository tests | Relevant executable artifacts; expensive environments. Keep public tests available to all arms and hidden evaluation separate. |
| Embodied textual planning: [ALFWorld](https://github.com/alfworld/alfworld) | Plan to admissible action; environment state and preconditions | Native goal completion | Repeated action structure, comparatively lighter text mode. Requires adapter reset/resume verification. |

This is a **shortlist**, not a claim of completed adapters or a commitment to run all four.
AppWorld is the leading next-domain candidate because observable state changes can make
handoff constraints substantive. WorkArena can have service-account dependencies. The
local Docker CLI exists but its Linux daemon was unavailable during the read-only check;
WSL has Ubuntu installed. No system services were changed during this audit.

Native benchmark familiarity is reported explicitly. Fairness requires the same adapter,
tools, observations, memory-placement policy and budget for all adapted arms; it cannot be
established simply by saying that no baseline is native to the benchmark.

## Adapter promotion tests

- Reset reproduces the same public state, including files/database/browser session.
- Checkpoint copies isolate every arm's mutations.
- Tools cannot read hidden evaluation labels or future tasks.
- Identical actions produce identical deterministic environment transitions.
- Scoring uses the benchmark's unchanged evaluator; malformed outputs fail consistently.
- Timeouts, retries and partial completion are logged with per-arm cost.
- One no-memory and one control rollout reproduce expected benchmark behavior before
  any method-level comparison is run.

## Existing pinned vendor metadata

| Path | Gitlink commit | Status at audit |
|---|---|---|
| `vendor/ExpeL` | `e41ec9a24823e7b560c561ab191441b56d9bcefc` | Empty checkout; URL metadata repaired |
| `vendor/agent-workflow-memory` | `8c0ff8cd11d648c8fceb99e4e42f37e3b75381b1` | Empty checkout; URL metadata repaired |
| `vendor/ProphetNet` | `5cf70eb41cdaa1d8faa3e1265d95ee5792d49a53` | Empty checkout; URL metadata repaired |

Revision detection now returns unavailable for an empty vendor directory, rather than
incorrectly attributing the parent CoProCon HEAD to a baseline. No published reproduction
score is newly claimed.

## Append-only reproduction update: 16 September 2026

The two empty ExpeL and AWM submodules were populated at the exact gitlinks above;
no vendor source was edited. ProphetNet remains uninitialized. These checkouts
and restored URLs repair provenance, not scientific reproduction by themselves.

Native probes are saved under `artifacts/research/reproduction_probe_20260916/probes`:

- ExpeL `train.py --help`: exit 1 on the current Python 3.13.5 environment,
  missing `hydra`. Upstream specifies Python 3.9.17, OpenAI 0.27.7, LangChain
  0.0.181 and other older pins. It needs an isolated compatible environment;
  installing those pins into the user's current environment would be inappropriate.
- AWM native Mind2Web scorer: exit 0 on an authored score fixture; produced the
  expected 50% element accuracy, 75% action F1, 50% step success and 50% success.
  These are **fixture values**, not task performance or a benchmark reproduction.
- AWM's inference wrapper imports the OpenAI client and expects `OPENAI_API_KEY`.
  An OpenRouter transport adaptation needs explicit model/context/budget parity;
  merely reusing that environment variable is not evidence of a faithful baseline.

No benchmark episodes or paid baseline requests were run by these probes.
Run `python -m copromem.reproduction_probe` to repeat the bounded native checks.

## Later append-only update: isolated baseline environment and AppWorld source

See [the ExpeL native progress record](019_EXPEL_NATIVE_REPRODUCTION_PROGRESS.md)
for isolated Python-3.9.17 dependency resolution, unchanged vendor provenance,
recorded import failures and the distinction between component fixtures and
published-score reproduction. No ExpeL performance result is newly claimed.

The earlier AppWorld "not installed" and Docker-daemon observations above are
historical. A bounded isolated live/prefix-replay adapter and native evaluator now
exist. Cycles 6--8 each collected eight training episodes, all with native failure;
all their live/replay pairs matched. This is not an effective no-memory baseline
yet. [Cycle 8 and the next diagnostic](018_CYCLE08_RESULTS_AND_CODER_PREREGISTRATION.md)
record the current source gate. Other benchmark adapters remain unimplemented.

The ExpeL isolated environment now builds, `pip check` passes, and all three
unmodified native CLIs initialize. Six native parser/update fixture checks pass;
the initial failed fixture and an observed multiline-regex quirk are preserved
in [the completed progress record](019_EXPEL_NATIVE_REPRODUCTION_PROGRESS.md).
This upgrades ExpeL from an import failure to component-smoke-tested status,
**not** to published-score reproduction or an integrated comparison baseline.

The later [native retrieval check](019_EXPEL_NATIVE_REPRODUCTION_PROGRESS.md)
also passes: pinned real all-mpnet-base-v2 embeddings feed ExpeL's actual FAISS
dynamic-prompt path on authored histories. Self-task exclusion, shortest-trajectory
selection and budget filtering are exercised. The environment/LLM constructors
are bypassed and the token counter is a declared fixture stub. This remains
component-level reproduction; no native task or insight score is claimed.

AppWorld cycle 11 now supplies one success and one failure on the same build
scenario, with all eight episode replays verified. Source quality remains weak
(1/8 success), but no longer all-failure. See [the result and local cross-over
protocol](022_CYCLE11_RESULTS_AND_CROSSOVER_PREREGISTRATION.md). Other benchmark
adapters and a fair integrated baseline grid remain incomplete.

ExpeL now passes [a native ALFWorld reset/action/reward gate](024_EXPEL_ALFWORLD_NATIVE_GATE.md)
on one hash-selected train-only fixture. Current official text-data assets are
pinned, with the generated-game archive's later replacement disclosed. The
installed engine's temporary shared-library load required a separate bounded
executable temp mount; two initial failures and two successful repeats remain.
No agent policy, insight generation or published task score was reproduced.
ALFWorld has a native environment component check, **not** a completed canonical
paired-checkpoint adapter or integrated comparison suite.

## Cycle-14 baseline-priority revision

The [new primary-method audit](NOVELTY_MATRIX_20260916.md) identified AutoGuide
as an omitted, essential context-aware contrast-memory comparison. The updated
six-method priority shortlist is **ExpeL, AutoGuide, ReasoningBank, CONTRAMEM,
Skill-Pro and AgentSpec**, in addition to the mandatory causal controls. This is
a documented scientific priority change, not a claim these six are runnable.

AWM moves to the reserve list because the immediate hypothesis concerns scoped
contrast and intervention admission; preserve its source and scorer fixture.
It remains valuable if the contribution shifts toward workflow abstraction.
ERL is another reserve, especially for testing whether collecting paired outcomes
is worth the cost versus single-trajectory reflection. Neither method is rejected
on performance grounds. Final executable comparison arms still require provenance,
native checks, faithful shared adaptation and frozen resource accounting before
the pilot; a shorter runnable list must not be presented as full reproduction.

## Cycle-15 ReasoningBank provenance correction

[The official-source audit](029_REASONINGBANK_OFFICIAL_SOURCE_AUDIT.md) verifies
Google Research's linked repository at commit
`ed80611788292ea739f1effd31f16c53823b8a0d`. The unchanged checkout passes syntax
parsing for 97 Python files. Status advances to **official provenance and static
code audit**, not installed/runnable/reproduced. Its retrieval has cache writes,
cloud embedding dependencies and identity/lifecycle assumptions that require
explicit shared-harness tests. No score or task-policy execution is claimed.

Follow-up: ten [source-function lifecycle fixtures](029_REASONINGBANK_OFFICIAL_SOURCE_AUDIT.md#follow-up-isolated-source-function-cache-fixtures)
pass twice with identical outputs using toy embeddings in an isolated existing
torch image. Import startup and native dependencies are bypassed, so this is not
native ReasoningBank retrieval or policy reproduction. Retain its quirks and
account for any later adapter changes explicitly.

## Cycle-17 AgentSpec source/parser gate

[Pinned AgentSpec implementation and eighteen parser/interpreter probes](040_AGENTSPEC_PINNED_PARSER_AND_ENFORCEMENT_AUDIT.md)
now have repeatable local component evidence at revision
`e6fa3902e2cfb9681f454b355691b771f70543f8`. Native `Rule`/generated parser imports
are separate from exact interpreter-class-body fixtures with bypassed module
bootstrap. The reused runtime is not a resolved AgentSpec LangChain installation.
Source, grammar, trigger-input and dispatch discrepancies remain explicit; no
vendor fix, real recovery action, benchmark rollout or score is claimed. Before
comparison, reconcile these issues transparently and keep the baseline strong.
