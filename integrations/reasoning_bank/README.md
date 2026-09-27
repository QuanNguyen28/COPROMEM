# ReasoningBank integration

`upstream.patch` records the external ReasoningBank-side integration. The
importable CoProMem adapter lives at
`copromem.integrations.reasoning_bank.adapter`; this directory contains only
external-repository setup and execution assets.

Run `setup.sh` in a separately pinned ReasoningBank checkout, then invoke
`run_benchmark.py`. Neither script installs credentials or sends a provider
request during import.
