# fixed_dynamic_v3 retrieval-integration invalidation

Status: `INVALID-METHOD-INTEGRATION`; evaluation evidence is audit-only.

The frozen v3 manifest is
`31eebe51a0ce51e78f7ed9a51b143683240c0dfa4303a2f3ccda4443b2541816`.
Its 48 durable evaluation artifacts, journals, scorer records, append-only
ledger, lifecycle snapshots, failed-resume records, and forensic artifacts are
preserved locally under the ignored `artifacts/` tree and are not rewritten.

The local forensic audit found valid canonical artifact/history hashes, unique
trajectory keys, reconciled write-ahead action journals, reconciled scorer
before/after evidence, locked-route records, and no unresolved reservations.
It also found a systematic CoProMem retrieval-provenance failure: all completed
CoProMem Fixed records shared one injected-guidance hash, as did all completed
CoProMem Dynamic records; reconstructing guidance from the preserved bank and
durable task instruction did not reproduce those hashes. Consequently those
guidance records cannot be shown to be task-aware learned-memory retrieval.

The affected count is all 18 completed CoProMem evaluation trajectories. This
does not establish that any score is incorrect, but it invalidates comparative
interpretation of v3. The v3 diagnostic-only aggregates and checksums are in:

- `artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v3/forensic-audit-v1.json`
- `artifacts/research/official_reme_copromem_pilot/fixed_dynamic_v3/forensic-audit-v1-checksums.json`

No method ranking, efficacy, transfer, or generalization claim may use v3.
