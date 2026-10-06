# ALFWorld x CoProMem benchmark harness

This benchmark harness lives in `COPROMEM/benchmarks/alfworld-copromem`. The
official ALFWorld checkout is alongside it at `COPROMEM/benchmarks/alfworld`.
The runner uses its text-only environment against the existing CoProMem public
API without patching either codebase.

The default paired pilot evaluates the same six `valid_unseen` games with the
same model and seed under two arms: `no_memory` and `copromem_v2`. Games are
selected in repeated task-family pairs so successful CoProMem episodes can be
promoted and retrieved on a later task of the same structural family.

The CoProMem arm uses the structured adapter in `copromem_adapter.py`. For a
compatible retrieval it executes the returned decomposition DAG as observable
checkpoints, gates ALFWorld actions until predecessor milestones are verified,
and evaluates attached edge contracts. Retrieval vetoes and exploratory misses
remain ungated to preserve CoProMem's anti-lock-in behavior. Episode learning is
based on milestones actually observed in the environment, and paired No Memory
outcomes are sent back to the core's harm/quarantine feedback path.

Each new CoProMem episode records `adapter_version`, per-step gate decisions,
verified transitions, and a final controller summary in `episodes.jsonl`.
Previously completed episode rows are never rewritten.

Run a zero-provider smoke test:

```powershell
.\run.ps1 -Check
```

After setting `OPENROUTER_API_KEY` in `COPROMEM/.env`, run the pilot:

```powershell
.\run.ps1
```

Results are written under `COPROMEM/benchmarks/results/<run-id>`.
The launcher enforces the task, step, call, model-price, and total-cost caps from
the ignored `.env` file.

## ReasoningBank arm

`run_reasoningbank_experiment.py` is orchestration only. Its thin
`reasoningbank_adapter.py` layer imports retrieval, trajectory formatting,
success/failure prompts, client selection, and memory induction behavior from
the official `google-research/reasoning-bank` checkout pinned at commit
`ed80611` under `COPROMEM/external/reasoning-bank`. It does not maintain a local
reimplementation of ReasoningBank.

The adapter only translates ALFWorld's task and observable state/action history
into the upstream WebArena record shape. ALFWorld's objective `won` signal
replaces the WebArena judge. No hidden reasoning is synthesized: upstream's
`think_list` receives the visible state that preceded each action.

The upstream checkout is prepared reproducibly by:

```bash
bash COPROMEM/integrations/reasoning_bank/setup.sh
```

The ALFWorld environment additionally needs the lightweight official OpenAI
client used by the OpenRouter compatibility path:

```bash
alfworld-env-wsl/bin/pip install -r COPROMEM/benchmarks/alfworld-copromem/requirements-reasoningbank.txt
```

Validate the environment without provider calls:

```powershell
.\run_reasoningbank.ps1 -Check --tasks 2 --max-steps 60
```

Run the current sorted tasks 1–68:

```powershell
.\run_reasoningbank.ps1 --max-steps 60
```

Resume an interrupted run without replaying completed episodes:

```powershell
.\run_reasoningbank.ps1 --run-dir /mnt/d/aamas/COPROMEM/COPROMEM/benchmarks/results/<run-id>
```

The run directory contains `episodes.jsonl`, `reasoning_bank.jsonl`,
`query_embeddings.jsonl`, `summary.json`, and the continuously updated
`tracker.md`.

## Legacy ReMe arm

The ALFWorld ReMe adapter follows the pinned upstream `reme_v3` task-memory
contract. `record_task_memory` receives the upstream-required `workspace_id`,
`memory_dicts`, and `update_utility` fields. The in-memory vector store is
dumped atomically under `reme-task-memory/<workspace-id>.jsonl` after every
ReMe episode and is loaded before a resumed episode, so restarting the service
does not silently erase learned memories.

When resuming a pre-patch run that has no dump, the runner reconstructs the
bank from the exact `metadata.memory_list` objects already stored in completed
episode rows. It fails closed if the old metadata reports deletions without
identifying the deleted memories; it never replays completed model calls.

New runs intentionally start with an empty bank unless
`ALFWORLD_REME_SEED_SNAPSHOT` names an upstream vector-store dump directory
(or its correctly named `<workspace-id>.jsonl` file). Set
`ALFWORLD_REME_MAX_TOKENS` to control memory extraction separately from the
ALFWorld action model; it defaults to `ALFWORLD_MAX_TOKENS`, then 1024.
