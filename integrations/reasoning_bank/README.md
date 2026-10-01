# ReasoningBank integrations

`upstream.patch` records the external ReasoningBank-side integration. The
importable CoProMem adapter lives at
`copromem.integrations.reasoning_bank.adapter`; this directory contains only
external-repository setup and execution assets.

That legacy package targets **WebArena**. It is not an AppWorld baseline, and
its historical `--criteria gt` path uses benchmark reward for induction. Do
not use it for a paper-faithful ReasoningBank comparison on AppWorld.

The maintained AppWorld port is documented at
`research/reasoningbank_appworld/SETUP_AND_FIDELITY.md` and implemented in
`copromem.integrations.reasoning_bank.appworld`. It preserves upstream memory
semantics while sharing the native AppWorld executor/scorer with CoProMem.

Run `setup.sh` in a separately pinned ReasoningBank checkout, then invoke
`run_benchmark.py`. Neither script installs credentials or sends a provider
request during import.
