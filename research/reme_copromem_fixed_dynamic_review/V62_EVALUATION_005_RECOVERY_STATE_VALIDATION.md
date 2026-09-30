# v6.2 recovery-state and dual-domain custody validation

This is a zero-provider validation of the immutable Evaluation 004 recovery
prefix. It creates neither an Evaluation 005 directory nor a manifest.

## Hash domains

The prior mismatch was a domain-comparison error, not an artifact mismatch.
Both preimages are durable and reproducible with canonical JSON
(`ensure_ascii=False`, sorted keys, separators `,` and `:`, UTF-8, no trailing
newline in the hashed bytes).

| Domain | Identity | Exact preimage | Count |
|---|---|---|---:|
| Source artifact inventory | `c40daeba9baf334f073125a52f4aec5ff59bd86181e346983bd0f8250f33b122` | ordered full `v6.2-real-prefix-import-v1` source entries reconstructed from immutable artifacts | 20 |
| Successor envelope inventory | `d1b26a6e0e497deaf9660d000e737893f6a666b60fe68d38db7375b6542d32be` | ordered `atomic-recovery-import-v1.records` entries for the legacy `protocol=shadow` import | 20 |
| One-to-one custody mapping | `2565342c26ae97d38d04bc6cbcc7169785269fc81c7e9c38ee7c6c24017484aa` | ordered source-entry/artifact/envelope mappings | 20 |

The source inventory includes immutable source provenance and evidence
identities. The envelope inventory includes only `position`, `trajectory_id`,
and envelope hash; each envelope separately binds its full source entry. They
must therefore never be compared for equality. The older labels in the
initial handoff were reversed; this report preserves both values and records
their actual serialized objects rather than relabeling either hash.

The durable source reconstruction is the immutable Evaluation 004 evidence.
The durable envelope preimage is the completed atomic import marker and its
twenty envelope files under the zero-cost validation evidence root. No raw
task payload, journal content, or provider response is included here.

## State result

The state assembler validates the 20 scored envelopes, both CoProMem task
boundaries, all four ReMe Dynamic marker/snapshot/verifier records, both Fixed
states, and the carried ledger boundary. It derives:

- `completed=20`, `expected=300`, `imported_completed=20`, `newly_completed=0`;
- four completed trajectories for each registered arm;
- committed CoProMem state
  `1cff4e8192f853d9e835e7e6054346867a7b53584f0c9d61ee13b757885d0b75`;
- a non-mutating rejected task-2 boundary with the same semantic pre/post
  identity and a quarantined, retrieval-invisible candidate;
- ReMe Dynamic state
  `5871658adb09f4c74fc730aaa8c5e5a1025d5bd51187393b3e0a1cf3f7401a2a`;
- Fixed identities `add35eca3ccaa9780183a144328157db2c64b932e5b69a7e3d5b87fd4efc9448`
  (CoProMem) and
  `6c3bc799ec0beb034fd2b81ee0d5cbf6e89a14f3a5a39ebf70d34853686b00a0`
  (ReMe); and
- next work `09b0ee6_1 / no_memory / trial 1 / seed 11001`.

The Evaluation 004 ledger remains 268/268 settled with zero unresolved
reservations. The historical carry is separate and is never re-created as
successor activity.

The disposable zero-provider unified marker is
`e455c78ca68eb9db727f955639a903a3852b9f15ad16f135d4355decf81e36c8`.
It is a validation artifact only, not an Evaluation 005 marker.

## Admission result

**RECOVERY-IMPORT-READY.** The production recovery-start boundary accepts only
a content-valid unified marker with both domain identities and the validated
one-to-one mapping. It remains read-only before a runner lock, service, or
task dispatch.
