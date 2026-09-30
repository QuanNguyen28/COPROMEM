# v6.2 recovery-state validation

This is a zero-provider validation of the immutable Evaluation 004 recovery
prefix.  It creates neither a successor run directory nor a manifest.

## Result

The production state assembler validates the 20 scored envelopes, the two
CoProMem task boundaries, the four ReMe Dynamic marker/snapshot/verifier
records, both Fixed identities, and the carried ledger boundary.  It derives:

- `completed=20`, `expected=300`, `imported_completed=20`, and `newly_completed=0`;
- four completed trajectories per registered arm;
- the committed CoProMem state
  `1cff4e8192f853d9e835e7e6054346867a7b53584f0c9d61ee13b757885d0b75`;
- the non-mutating rejected task-2 boundary with the same semantic pre/post
  identity and a quarantined, retrieval-invisible candidate;
- the latest verified ReMe Dynamic state
  `5871658adb09f4c74fc730aaa8c5e5a1025d5bd51187393b3e0a1cf3f7401a2a`;
- Fixed identities `add35eca3ccaa9780183a144328157db2c64b932e5b69a7e3d5b87fd4efc9448`
  (CoProMem) and
  `6c3bc799ec0beb034fd2b81ee0d5cbf6e89a14f3a5a39ebf70d34853686b00a0`
  (ReMe); and
- next work `09b0ee6_1 / no_memory / trial 1 / seed 11001`.

## Fail-closed custody discrepancy

The supplied real-prefix inventory hash is
`d1b26a6e0e497deaf9660d000e737893f6a666b60fe68d38db7375b6542d32be`.
The current, committed importer recomputes the complete ordered envelope
inventory from the immutable source as
`c40daeba9baf334f073125a52f4aec5ff59bd86181e346983bd0f8250f33b122`.

These are different content identities.  No source artifact was changed to
make them agree.  A future recovery run must not be admitted until the earlier
hash's canonical serialization is recovered and shown to bind the exact same
twenty immutable envelopes, or the discrepancy is resolved by an explicit,
versioned custody decision.  The recovery-start admission boundary deliberately
does not acquire a lock or create a runtime object before this provenance is
accepted.

The disposable zero-provider validation marker was
`7a5f076e17ecc07f3aab6c6acb77ea15718cbff60b95a87ec65d1abb3852d6e9`.
It is not a run artifact and is not used as a successor marker.
