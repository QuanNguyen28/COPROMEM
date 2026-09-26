# ReMe–CoProMem fidelity audit

## Evidence inspected

* ReMe paper: arXiv `2512.10696v2` and ACL Findings 2026 paper.
* Official ReMe `main` at `8b5456641fc31e68c3a612753aa6d6692b83de2d`.
* Official `reme_v3` at `2f37a159b72a04ac1885a7db7f1a663a833e7791`.
  This branch contains the relevant `test/cookbook/bfcl` and
  `test/cookbook/appworld` runners plus procedural-memory extraction code.
* CoProMem at `6eca54ca14a7935fcdcdc1a9a77319ed113a0679`.

The live ReMe `main` is no longer the paper experiment implementation: it is
a file-native memory system.  Therefore using it unmodified would not be a
faithful ReMe paper comparison.  The paper-era `reme_v3` branch is the
appropriate code reference, but the planned DeepSeek setup remains an
adaptation because the paper reports Qwen3-8B settings.

## ReMe behavior confirmed from the paper-era code

`reme/extension/procedural_memory` classifies trajectories into success and
failure, extracts success and failure insights, can extract comparative
success/failure insights, validates/deduplicates memory, retrieves top-K
(default 5), and updates retrieved-memory frequency and utility.  Its BFCL and
AppWorld runners expose deletion frequency `5` and utility threshold `0.5`.
This maps to the requested dynamic parameters alpha=5 and beta=0.5.  The
published runners do not by themselves establish the requested N=8, four
evaluation trials, or three seeds; those are strengthened protocol choices and
must be implemented visibly in the common harness.

ReMe fixed is defined here as frozen after acquisition.  ReMe dynamic keeps
the same recall and distillation but permits the paper-era utility/deletion
path.  This distinction must be checked by a unit test that verifies no
post-acquisition write/delete call in fixed mode and at least the configured
metadata/deletion behavior in dynamic mode.

## Current CoProMem behavior

* **Stored representation:** `ProceduralMemoryItem` records (intent, procedure,
  constraints, source, domain, success) alongside `DecompositionSchema` DAGs,
  optional contracts, episodic traces, a fast buffer, and an admitted schema
  bank.
* **Acquisition:** successful trajectories induce positive procedural memory;
  episodes and schemas enter a buffer and consolidation/admission controls slow
  retrieval. Failed episodes remain episodic evidence but are not positive
  procedure items. The comparison adapter gives every trace and induced memory
  a task-ID/seed/trajectory-index identity.
* **Retrieval:** ReasoningBank and naive semantic-RAG paths choose lexical
  Jaccard matches.  `copromem_v2` builds a current structure, filters compatible
  observed memories, applies pattern separation (semantic 0.40, causal 0.35),
  and may offer an alternative or exploration.  Its current default avoids
  contract guidance in the prompt. It is not memory-disabled: the comparison
  adapter removes generic defaults only to match the other arms' prior data.
* **Evaluation:** BrowserGym/WebArena code uses task reward/termination and may
  use a fuzzy judge; action acceptance is observable, but general semantic
  milestone verification is explicitly not implemented.

## Comparability risks and required controls

| Risk | Control / status |
| --- | --- |
| ReMe code drift | Pin `reme_v3`; retain `main` SHA as audit evidence. |
| Model mismatch with paper | Label all outputs DeepSeek adaptation; do not compare as reproduction. |
| CoProMem benchmark mismatch | Build a common BFCL/AppWorld harness; do not use its WebArena result as evidence. |
| Information asymmetry | Equal acquisition IDs, N=8 ceiling, 30 iterations, tools, and one start-of-task retrieval. |
| ReMe failure pairing vs CoProMem | Report as unavoidable mechanism difference and run stated CoProMem ablations separately. |
| Scorer drift | Pin BFCL/AppWorld revisions and execute their official scorers unchanged. |
| Prior exposure | Run and preserve the manifest/source/artifact exposure audit before evaluation. |
| Existing test failure | Full CoProMem pytest currently stops in collection: missing `gymnasium`. No paid run permitted. |

## Current blocking state

The active environment lacks `gymnasium`, BrowserGym/WebArena, Playwright, and
the external ReasoningBank checkout required by one collected CoProMem test.
The full suite has not passed.  The repository must be installed in a clean,
pinned environment (including its `benchmark` extra and ReasoningBank setup),
then all tests and scorer smoke tests must pass before a budget gate can open.
