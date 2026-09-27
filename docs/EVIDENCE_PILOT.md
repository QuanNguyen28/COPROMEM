# Local pilot: evidence-gated procedural memory

This pilot asks whether measured transfer outcomes can improve the decision to
inject a procedural memory. It is a development study on five WebArena Shopping
Admin evaluation tasks, not a SOTA benchmark or a clean held-out claim.

The source bank contains three procedures from archived successful tasks. For
each source family, two different calibration tasks are run with no memory and
with the existing ungated COPROMEM retrieval. A paired beneficial flip is a
failure without memory and a success with it. A harmful flip is the reverse.
For the same template and structural constraint signature, the evidence gate
requires two calibration pairs, at least one beneficial flip, and zero harmful
flips; otherwise it abstains. The state is frozen before evaluation, so neither
evaluation outcome nor evaluation-generated schema can update the bank.

## Prepare

```bash
python scripts/run_local_evidence_pilot.py prepare
```

This uses only archived JSONL and task configuration files. It writes a
manifest and initial state to `artifacts/local_evidence_pilot_v1/`. It never
deserializes BrowserGym pickle artifacts. The allocation, source checksum,
model and protocol are recorded in the manifest.

## Run

The runner requires a local WebArena Shopping Admin service and Ollama with
`qwen3.5:9b`. It also requires an executable reset hook supplied as
`--reset-hook PATH`. The hook receives the task ID, restores the *complete*
website state from the same frozen snapshot before each arm, and prints only
the lowercase SHA-256 digest of that restored state. A hook that hashes only a
page or task config does not meet this requirement. The runner additionally
requires identical initial screenshot hashes across arms. It stops when either
check fails.

```bash
python scripts/run_local_evidence_pilot.py run --reset-hook /path/to/reset-and-hash
```

The runner accepts only loopback HTTP endpoints, clears provider API keys,
uses Ollama's OpenAI-compatible endpoint, and blocks nonlocal Python socket
connections in the agent process. Selected tasks use native `exact_match` or
`must_include` scoring; any task requiring an LLM judge is rejected during
preparation. The existing WebArena checkout is used without copying over its
adapter; the agent process loads the tracked adapter from `integrations/`.

Results and selection reasons are recorded per arm, with a `report.json` at
the end. The pilot's `go_signal` requires beneficial flips on two independent
template families, at most one harmful flip, and greater total success than
ungated retrieval. A positive signal only warrants a separate, larger study
with clean data and official baselines; a negative signal ends this candidate.

The historical research ledger records that previous AppWorld configurations
and existing benchmark artifacts do not establish an automatically learned
memory advantage. This pilot does not reinterpret those results.

## Local easy/medium 30-task extension

`scripts/run_local_easy_medium_30.py` extends the same paired design to 30
distinct Shopping Admin tasks from the curated WebArena easy and medium tiers:
15 easy and 15 medium. Three separate archived successful tasks seed the memory
bank. Six of the 30 tasks calibrate the gate; the other 24 are evaluated with
no memory, ungated memory, and evidence-gated memory. Tasks with an LLM judge,
state-changing objective, or potential source-answer leakage are excluded.

The run uses the `copromem` Conda environment and local Ollama Qwen 3.5 9B.
The image `copromem-qwen3.5-9b-16k:latest` contains the same model weights with
`num_ctx=16384`; the unmodified Ollama model's 4096-token context truncates
WebArena prompts. A SHA-256-verified static `cl100k_base` tokenizer file is
cached before starting; agent processes stay on loopback. The local Magento
snapshot is `copromem-shopping-admin-pilot:local`; its immutable image ID is
checked by `scripts/reset_local_shopping_admin_pilot.sh`, which recreates the
site container before every arm. The original `shopping_admin` container is
left alone.

The initial screenshot check ignores only the dashboard Bestseller table area,
whose tied rows can appear in a different order after the same snapshot is
restored. Raw screenshot hashes are retained in every arm result. The runner
refuses to overwrite completed arms and can resume by running the same command.
Results are under `artifacts/local_easy_medium_30/`, with `report.json` created
only after all 30 tasks finish. A positive result here would remain a
development result, not a SOTA claim.

```bash
/home/levantuananh/anaconda3/envs/copromem/bin/python \
  scripts/run_local_easy_medium_30.py run \
  --reset-hook scripts/reset_local_shopping_admin_pilot.sh
```

## Current workspace status

As inspected on 25 September 2026, the existing `shopping_admin` container is
stopped, its image redirects `/admin` to `metis.lti.cs.cmu.edu`, and the
WebArena checkout has no `.auth/shopping_admin_state.json`. No reset hook that
proves a complete restored site state is present. The runner therefore stops
at preflight; no new rollout or pilot outcome has been collected. Configure a
local-only site snapshot, generate valid auth state from that snapshot, and
provide a reset hook before interpreting paired results.
