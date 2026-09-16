# ExpeL native reproduction progress

Recorded 2026-09-16. This is an append-only engineering record, **not a report of
reproduced ExpeL benchmark scores**. No model calls, embedding downloads, task
trajectories or learned rule induction are claimed by the checks below.

## Provenance and scope

Official checkout: `vendor/ExpeL`, commit
`e41ec9a24823e7b560c561ab191441b56d9bcefc`, unchanged and clean. Existing source and
the user's documents are preserved. Reproduction records live under
`artifacts/research/expel_native_probe_20260916`.

The native code specifies Python 3.9.17 and older dependencies, including
LangChain 0.0.181, OpenAI 0.27.7, Hydra 1.3.2 and Transformers 4.30.2. Installing
these into the user's Python 3.13 environment would conflate environments. The
research scripts therefore use a separate Docker image based on
`python:3.9.17-slim@sha256:42a5da33675ec5a692e8cdbb09ffa4e39588c10dd9a96235e543c498484ee18e`.

Only explicit build recipes and dependency lists enter the build context. Runtime
probes mount the pinned vendor checkout read-only, with no API key, `.env`, parent
workspace, Docker socket or task-solution mount. They run as user 10001, without
network or capabilities, with a read-only root, bounded temporary storage, CPU,
memory, process count and timeout. A timeout may stop only the labelled container
owned by the probe. Raw outputs and unsuccessful attempts remain in the archive.

## Completed minimal-environment attempts

The initial import-only environment built as image
`sha256:e1ba9148ebb3c963ad8efcd468a0b80a809d133776bb85e8bc11af0312a39ce5`.
Its scope was intentionally partial; missing dependencies were not treated as a
working baseline. A Windows-console Unicode logging exception interrupted the
parent log reader while Docker continued. The build was **not restarted**: its
BuildKit history and resulting image were recovered. The parent CLI exit status
is unknown, explicitly recorded in
`build_recovery/07f41c048f61ff1723f5ac54cce640f15b9ebde9627bfce1554de409af4ba9ce.json`.
The logger now preserves UTF-8 raw output and escapes only unsupported console
characters.

Native `train.py --help`, `insight_extraction.py --help`, `eval.py --help` and an
authored fixture importing `agent.expel` first failed while ALFWorld tried to
create `/.cache` under the read-only root. Declaring `ALFWORLD_DATA=/tmp/alfworld`
and `XDG_CACHE_HOME=/tmp/cache` resolved that particular runtime-path issue without
changing vendor code or algorithm behavior. Each retry has a different immutable
probe key and retains the original failure.

The four probes then failed importing `termcolor`. Installed ALFWorld 0.3.5 eagerly
imports multiple environment backends, even for a rule-function or CLI-help probe.
This is not the same as current upstream master, whose imports were later made
lazy. `pip check` also reported the deliberately missing ALFWorld dependencies.
The environment metadata probe succeeded; that does not make the algorithm run.

Representative corrected-path failure records:

- Train help: `native_probes/2a9fea3a4f109ecd33ec0773eab0ca6bf119432105739216be7a1475a30cea34.json`.
- Insight help: `native_probes/d68d6c48305ff470252f77a5cec209bf0d391424b1ffe173e9a25b37bd886a89.json`.
- Eval help: `native_probes/c2e62d18065775f8aa08750549eea85064f2abf9bf2ab37f6e5a646477de0ba9.json`.
- Rule fixture: `native_probes/936041e47ff928d285e00e545e3aa61425d4a716ba5af0f71b0bdeceaffcd57d.json`.

## Full dependency-resolution attempts

The next recipe copies the exact upstream requirements and adds explicit CPU and
compatibility constraints in `research/containers/expel/constraints-full.txt`.
It installs Torch 2.0.1+cpu and torchvision 0.15.2+cpu from the official CPU index,
ALFWorld 0.3.5, termcolor and FAISS CPU, plus native build libraries. NumPy/SciPy,
Pydantic, sentence-transformers, Hugging Face Hub and other compatibility pins
are transparent downstream choices, **not proof of the original paper's exact
environment**. Pip install reports record downloaded distribution hashes. The
image also contains apt packages and transitive resolution not fully hash-locked;
an image ID alone is not a complete historical reproduction recipe.

Attempt 1 failed during dependency resolution: SpaCy 3.8.16's source-build path
requested a NumPy version unavailable for Python 3.9. Full raw output is in
`builds/121b3eee5cc7c4be2837d9fa3afa246a80f5d839182e626ce0105a80cfe8bc91.json`.
That first full attempt's generic interpretation string still says import-only;
this entry clarifies its actual full-requirements scope without rewriting it.

Attempt 2 pins SpaCy 3.6.1, whose Python-3.9 wheel is available. The changed context
has source ID `de63555d07f385cb5236e2148b08a10cd1baff0202d94bad3b39e3b3496cb6a0`.
At this entry it is still building and must not be described as successful. The
earlier failed context is retained; no vendor patch or evaluator alteration was
used. Slow downloading is live progress, not evidence that reproduction is
impossible.

## Native component check and remaining fidelity work

The authored fixture calls the **unmodified** native `parse_rules` and
`update_rules`. It checks period-terminated operations, ADD/AGREE/REMOVE counters,
the stronger full-bank removal and duplicate addition handling. Expected values
come from code inspection and are fixture assertions, not learned performance.
At this entry import failures mean the fixture has not yet executed successfully.

Once dependency setup passes, the next checks are CLI initialization, this native
component fixture, a real embedding/retrieval smoke test, and a native original-
environment rollout using an explicitly registered dataset/model configuration.
The code's `gpt`-name-based model wrapper and old API require a declared transport
adaptation for other providers; pretending an arbitrary Qwen model is GPT would
not be faithful reproduction. ALFWorld datasets and native goal scoring must be
verified independently before any performance claim.

Only then adapt ExpeL to the same AppWorld observation/action/checkpoint and budget
interface as the other methods, saving the adaptation diff and the native-to-
adapted comparison. A working `--help`, parser fixture, or dependency check is
engineering progress, not a reproduced paper score or fair comparison by itself.

Current decision: **REVISE** dependency environment while preserving the baseline
algorithm. There is no evidence-based reason to discard ExpeL merely because its
old package graph needs an isolated compatible environment.

## Attempt-2 result and next dependency revision (same day)

Attempt 2 ended with exit 1. SpaCy's pinned wheel resolved the earlier problem,
but TextWorld 1.6.1 is source-only for this platform. Its native `setup.sh` tried
to download the Inform7 CLI over HTTP and failed because `curl` was unavailable.
All output is retained in
`builds/de63555d07f385cb5236e2148b08a10cd1baff0202d94bad3b39e3b3496cb6a0.json`.

The next recipe explicitly selects TextWorld 1.6.2, still within ALFWorld 0.3.5's
declared `textworld[pddl]>=1.6.1` range. PyPI metadata was checked: a Python-3.9
Linux-amd64 wheel exists with SHA256
`a958872fd4cdbec8b3ef9fc14be07f97b0e360e9dddd73156bd1f3871b9d3f69`.
The installer requires a binary TextWorld distribution and fails rather than
falling back to that source installer. This is a disclosed dependency change,
not an unchanged historical environment or proof of task-behavior equivalence.

The recipe now requests ALFWorld's full extra, consistent with the native
baseline's broader environment imports, and uses a BuildKit pip-cache mount to
avoid redundant downloads on later dependency repair. The cache contains public
packages only and is neither copied into the final runtime nor exposed to agents.
No model/data/evaluator code changes are made. A new immutable build-context
record will distinguish this attempt from both earlier failures.

## Attempt 3 and native component results (same day)

Attempt 3 completed with exit 0. Source ID:
`04dda3cc1c5cc17b6be02c6f053da1d07ce85c80e1742da78d90406c091a09d0`.
Immutable image:
`sha256:81bddf9a168c6b80d4ecf30f35cf1a96a5646ef823cfecb5958d90ccb9a6a5a3`.
The exact copied upstream requirements still hash identically to the vendor file.
Vendor commit/source remains unchanged. The dependency check passes.

All three native CLI-help commands now exit 0 in the isolated, network-free
runtime: training, insight extraction and evaluation. Their records are
`80eca50540fd75aff2c2d63c924132bb19a65f3a2b4591813596b2bd216274c6`,
`94f69b6b81e379f4a5d5f7e1dea51dd34735fdf10991adec5d6aa5dfb9f8ca81`,
and `43befd0151307e83db7b9ad386d734456961fc8f707743e01775ac78908707de`
under `native_probes/`. This confirms initialization, not task execution.

The initial rule fixture **failed** an authored expectation. Observation revealed
that the native regex's optional prefix permits whitespace/newlines: an unfinished
`ADD` line can absorb the following `AGREE` label, producing another ADD operation.
The original failed assertion and a diagnostic print are preserved in
`native_probes/6375d5935cd2e11571975a2fd1225a62e6c6d1794cf88faa2066cce39eb5fefa.json`
and `native_probes/89f3d5f688db98664c572cd211e10e4cbda21aa9470ac527dd59361768c21699.json`.
This corrects the earlier expectation that an unfinished line would always be
discarded without affecting a neighboring operation. No native parser fix was
made and no benchmark output was relabelled.

A revised **descriptive** fixture checks valid operations, rejection of an isolated
unfinished line, the observed multiline quirk, update counters, stronger full-bank
removal and duplicate handling. All six checks now pass against the unmodified
native functions. Record:
`native_probes/900b97d35205a90fd907c60ee48c5e9f0c9119b095adc94a0f15eff98b675352.json`.
The fixture is not a success/failure induction experiment or evidence that the
parser is correct for arbitrary model output. A faithful adaptation must preserve
or explicitly disclose repairing this native behavior.

Consolidated probe report:
`reports/f78d9656e8b873e52eb47f893c0715b4e7c4fb2fd0488ad34e45e11e876c3142.json`.
The environment record `native_probes/cfbde6f95d3198fc3f06362dfe99426f455e13bc431a3f699c20d479c13743c8.json`
contains the pip installation reports and distribution provenance.

One build-engineering correction is also required: despite the added mount at
`/root/.cache/pip`, the declared `XDG_CACHE_HOME` led pip to store build caches at
`/tmp/cache/pip`. The earlier claim that this attempt's package cache would be
excluded from the final image is therefore inaccurate. Its public package cache
may occupy image layers; the runtime's fresh `/tmp` mount hides it from probes.
No secrets entered the build. A future recipe can explicitly set `PIP_CACHE_DIR`
to the mount; the saved successful image and failed attempts are not deleted or
silently replaced for this cosmetic/cache issue.

Decision for this completed environment/component cycle: **KEEP** the compatible
isolated environment and observed native-function fixture. Full published-score
reproduction, actual embedding/retrieval, native task rollout and fair AppWorld
adaptation remain incomplete. No paid model call or benchmark success is claimed.

## Pinned real embedding and native retrieval component (same day)

The next offline fixture now passes. It uses the unchanged upstream
`ExpelAgent.setup_vectorstore` and `update_dynamic_prompt_components`, not a
replacement nearest-neighbor implementation. Source inspection matters here:
the configuration mentions a KNN retriever, but this dynamic-prompt path actually
constructs a LangChain FAISS vector store and applies native task/environment,
length, current-task and duplicate filters.

The official [all-mpnet-base-v2 checkpoint](https://huggingface.co/sentence-transformers/all-mpnet-base-v2/tree/e8c3b32edf5434bc2275fc9bab85f82640a19130)
is pinned at `e8c3b32edf5434bc2275fc9bab85f82640a19130`. Eleven selected assets
were downloaded; no pickle weights, repository Python, ONNX or OpenVINO variant
is included. Downloaded Git blobs are checked against upstream blob IDs and
the 437,971,872-byte safetensors file against upstream LFS SHA256
`78c0197b6159d92658e319bc1d72e4c73a9a03dd03815e70e555c5ef05615658`.
Every selected file also has a local SHA256 in embedding manifest
`0aecf08cba0f1f1a6279c493e06e2f7f813be2b987f48227a4748586bdb28b45`.
Pinned upstream metadata and download failures, if any, have separate namespaces.
Existing files are verified, never silently overwritten.

The same full Python-3.9.17 image above runs with network disabled, root/model/
vendor read-only, user 10001, no capabilities or credentials, 2 CPUs, 2 GiB RAM,
256 MiB temporary storage and a 120-second supervisor timeout. Offline model
loading is explicit. Only installed stock model modules and local safetensors
are used; the benchmark dataset and AppWorld artifacts are not mounted.

Authored fixture: `research/fixtures/expel_native_retrieval.py`.
Native probe record:
`native_probes/912635dea1de36305b9eb835301c8a1c95a73fbc325ce755a8e975c44dc05600.json`.
Seven checks passed with exit 0:

- Finite 768-dimensional embeddings, repeatable on CPU within absolute 1e-6.
- Native task/environment filtering indexes exactly four authored task documents.
- A nearest exact self-task is excluded from retrieved examples.
- A long near-match is excluded; the shortest trajectory for the related task is selected.
- Repeated native retrieval selects the same example.
- A one-word fixture budget excludes all trajectories.

The first item includes two separate assertions. The loaded model reports a
384-token maximum sequence length. Observed squared-L2 ranks are approximately
0 (self), 0.17454 (over-budget), 0.31082 (selected related), 1.90803 (unrelated).
Those are fixture outputs, not a retrieval-quality evaluation.

Important boundaries: the native agent's environment/LLM constructors are bypassed
using a controlled instance. Histories are human-authored; their placement in a
success-history dictionary is a test input, not a claim of environment success.
The token counter is an explicitly disclosed word-count stub for exercising the
budget branch, not the production tokenizer. Native prompt-history replacement,
task rollout, critique/insight generation and shared AppWorld adaptation are not
validated by this initial-empty-history fixture. Local embedding inference occurs;
there are **zero paid model calls**, not zero computation.

Decision: **KEEP** this bounded native retrieval/environment check. Reproduction
is still component-level, and no ExpeL or CoProCon performance gain is established.
The next baseline gate is native environment/action/scorer execution and full
model/tokenizer wiring with explicitly disclosed transport changes. Separately,
the running cycle-11 collector remains frozen and is unaffected by this work.

After an import-order-only formatting change, the native retrieval fixture was
rerun rather than treating changed source as the old invocation. It again passed
all seven checks with the same observed ranks/selection. New record:
`native_probes/c23919a9e6812e0af0debd9fb565edfb49dbdeb7b20e815f7dadb231c66a9222.json`.
The previous successful record and its exact fixture remain archived. Six host
tests additionally check Git/LFS verification, size/hash corruption rejection and
the no-pickle/no-remote-Python download allowlist.
