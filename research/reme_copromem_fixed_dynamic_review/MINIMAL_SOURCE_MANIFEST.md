# Minimal source manifest

This branch is a maintained development package. It intentionally contains no
experimental run evidence, task payload, credential, downloaded benchmark, or
runtime environment.

## Canonical components

| Component | Canonical location | Supported entry point |
|---|---|---|
| CoProMem core and schemas | `src/copromem/{bank,contracts,schema,decomposition,pattern_separation,copromem_memory_module,workflow}.py` | Python imports from `copromem` |
| CoProMem Fixed/Dynamic AppWorld lifecycle and reproducible retrieval | `src/copromem/benchmarks/appworld/adapter.py` | `CoProMemAppWorldAdapter.retrieve_with_provenance()` / `reproduce_retrieval()` |
| Native AppWorld boundary | `src/copromem/benchmarks/appworld/worker.py` | `python .../worker.py` (JSON-lines) |
| AppWorld acquisition integrity | `src/copromem/benchmarks/appworld/acquisition.py` | `AcquisitionJournal` |
| WebArena integration | `src/copromem/benchmarks/webarena/` | loader, benchmark, evaluator imports |
| Official-upstream ReMe bridge | `src/copromem/integrations/reme/` | `corrected_service`, `upstream_executor`, bank/lifecycle APIs |
| ReasoningBank integration | `src/copromem/integrations/reasoning_bank/adapter.py` and `integrations/reasoning_bank/run_benchmark.py` | `COPROMEMReasoningBankAdapter` / shell setup |
| Frozen-run orchestration | `src/copromem/experiments/reme_copromem/` | `python -m copromem.experiments.reme_copromem.config` |
| Launch templates | `scripts/reme_copromem/` | `launch_fixed_dynamic.sh` or `.ps1` |

The runner requires local ignored inputs: `COPROMEM_RUN_DIR`, a frozen
manifest and `COPROMEM_ACQUISITION_POOL`; it never reaches into a historical
experiment directory. External runtime locations are explicitly configured
with `COPROMEM_REME_SOURCE`, `COPROMEM_APPWORLD_PYTHON`,
`COPROMEM_APPWORLD_ROOT`, and `COPROMEM_REME_PYTHON`.

## Compatibility shims retained

Only test-reachable public imports remain:

- `copromem.appworld_comparison_adapter` re-exports the canonical AppWorld adapter.
- `copromem.appworld_acquisition_gate` re-exports the canonical acquisition journal.

## Excluded groups

- v1-v3 and v4-specific runners, reports, reconciliation scripts, failed
  preflights, canaries, and transport experiments: superseded historical work.
- raw trajectories, payloads, journals, ledgers, scores, provider responses,
  logs, and result artifacts: local audit evidence, not source.
- virtual environments, caches, Ray/AppWorld runtime state, downloaded data,
  and vendored upstream source: external reproducible dependencies.
- credentials and `.env` files: secret material.
