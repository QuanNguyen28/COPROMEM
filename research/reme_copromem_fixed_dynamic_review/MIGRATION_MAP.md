# Migration map

| Old path | Canonical path |
|---|---|
| `src/copromem/appworld_comparison_adapter.py` | `src/copromem/benchmarks/appworld/adapter.py` |
| `src/copromem/appworld_acquisition_gate.py` | `src/copromem/benchmarks/appworld/acquisition.py` |
| native AppWorld preflight/live helpers | `src/copromem/benchmarks/appworld/worker.py`, `scorer.py` |
| `src/copromem/webarena_browsergym_benchmark.py` | `src/copromem/benchmarks/webarena/benchmark.py` |
| `src/copromem/webarena_loader.py` | `src/copromem/benchmarks/webarena/loader.py` |
| `src/copromem/webarena_evaluator.py` | `src/copromem/benchmarks/webarena/evaluator.py` |
| `research/official_pilot/reme_bank.py` | `src/copromem/integrations/reme/bank.py` |
| `research/official_pilot/evaluation_lifecycle.py` | `src/copromem/integrations/reme/lifecycle.py` |
| `research/official_pilot/reme_service.py` | `src/copromem/integrations/reme/service.py` |
| `research/official_pilot/corrected_reme_service.py` | `src/copromem/integrations/reme/corrected_service.py` |
| `research/official_pilot/locked_openrouter.py` | `src/copromem/integrations/reme/transport.py` |
| `research/official_pilot/upstream_executor.py` | `src/copromem/integrations/reme/upstream_executor.py` |
| `research/official_pilot/five_arm_runner.py` | `src/copromem/experiments/reme_copromem/runner.py` |
| `scripts/run_fixed_dynamic_v4.py` | `src/copromem/experiments/reme_copromem/config.py` |
| v4 reconciliation/report builders | `src/copromem/experiments/reme_copromem/reconciliation.py`, `reporting.py` |
| `integrations/reasoning_bank/copromem_adapter.py` | `src/copromem/integrations/reasoning_bank/adapter.py` |
| ReasoningBank setup/run scripts | `integrations/reasoning_bank/setup.sh`, `run_benchmark.py` |
