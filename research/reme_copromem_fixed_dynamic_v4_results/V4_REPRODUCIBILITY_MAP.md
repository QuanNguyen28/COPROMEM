# v4 reproducibility map

- Experiment branch: `experiment-reme-copromem-fixed-dynamic-v4`
- Exact experiment code: [`28d3dab36cb12ea03572376ab1fee35423c50871`](https://github.com/QuanNguyen28/COPROMEM/tree/28d3dab36cb12ea03572376ab1fee35423c50871)
- Review branch: `reme-copromem-fixed-dynamic-review`
- Review package commit at generation: `bb42f91020ff930c0bf87219ecad628f09b5c10a`
- Manifest SHA-256: `ded3741ee2c03bd0b54be1d9326121af113ed28595ea32c396facc8aff8a4460`
- Final report SHA-256: `ce92a1b4ebd718845461708723bde0add6b6337c1781f88fcafdcb8e588e28af`

| Exact v4 runtime file | Canonical review replacement | Difference |
|---|---|---|
| `scripts/run_fixed_dynamic_v4.py` | `src/copromem/experiments/reme_copromem/config.py` | explicit local run/acquisition input configuration; no historical artifact lookup |
| `research/official_pilot/five_arm_runner.py` | `src/copromem/experiments/reme_copromem/runner.py` | canonical digest, journaling and common executor boundary |
| `research/official_pilot/upstream_executor.py` | `src/copromem/integrations/reme/upstream_executor.py` | reviewed native-worker path and environment configuration |
| `research/official_pilot/reme_bank.py` / `evaluation_lifecycle.py` | `src/copromem/integrations/reme/bank.py` / `lifecycle.py` | same maintained ReMe integration boundary |
| `src/copromem/appworld_comparison_adapter.py` | `src/copromem/benchmarks/appworld/adapter.py` | compatibility shim removed except for test-reachable public import |

## Required local environments

Keep AppWorld and pinned ReMe in separate environments. Configure `COPROMEM_RUN_DIR`, `COPROMEM_ACQUISITION_POOL`, `COPROMEM_REME_PYTHON`, `COPROMEM_REME_SOURCE`, `COPROMEM_APPWORLD_PYTHON`, `COPROMEM_APPWORLD_ROOT`, and `OPENROUTER_API_KEY` without committing values. The pinned review package declares `agentscope==1.0.20`, `flowllm[reme]==0.2.0.10`, and `ray==2.58.0` in its ReMe optional group.

## Zero-paid-call verification

```powershell
$env:PYTHONPATH = "$PWD\src;$PWD"
python -m pytest -q tests\appworld tests\webarena tests\reme_copromem
python research\reme_copromem_fixed_dynamic_v4_results\build_v4_results.py --evidence <local-run-dir> --output research\reme_copromem_fixed_dynamic_v4_results
```

A future run uses `scripts/reme_copromem/launch_fixed_dynamic.sh` after placing a frozen manifest and frozen acquisition export under the ignored `COPROMEM_RUN_DIR`; do not run that command merely to regenerate this report.

Excluded by design: raw artifacts, task payloads, prompts, completions, memory text, journals, ledgers, logs, environments, caches, datasets, and credentials.
