# v6.2 recovery custody hash domains

## Source artifact inventory

- Semantic object: the ordered complete source entries returned by
  `v62_recovery_prefix.validate_real_prefix`.
- Schema/version and domain tag: `v6.2-real-prefix-import-v1` /
  `v6.2-source-artifact-inventory-v1`.
- Serialization: JSON with `ensure_ascii=False`, lexicographically sorted
  mapping keys, list order retained, compact `,`/`:` separators, UTF-8
  encoding, and no newline included in the digest.
- Path policy: generated E-backed artifact/root locators are projected to the
  legacy `E:\\...` spelling before hashing. This preserves the original
  Windows marker identity when the same durable files are read from WSL as
  `/mnt/e/...`; artifact-stored evidence paths and all content hashes remain
  untouched. It is consequently a custody identity, not a filename-free
  schema hash.
- Included per item: position, trajectory identity, immutable artifact/hash,
  source run/manifest/runtime/commit, journal/scorer/registry identities, and
  source paths used to read those immutable files.
- Excluded: successor recovery metadata and copied-file locations.
- Count: 20. Reconstructed identity:
  `c40daeba9baf334f073125a52f4aec5ff59bd86181e346983bd0f8250f33b122`.

## Successor envelope inventory

- Semantic object: `atomic-recovery-import-v1.records` for the completed
  legacy `protocol=shadow` import.
- Schema/version and domain tag: `atomic-recovery-import-v1` /
  `v6.2-successor-envelope-inventory-v1`.
- Serialization: the same canonical compact JSON/UTF-8 algorithm; records
  retain their frozen list order and have no digest newline.
- Included per item: `position`, `trajectory_id`, and the full successor
  envelope hash.
- Excluded: the envelope body, source payloads, journals, and copied paths.
- Count: 20. Reconstructed identity:
  `d1b26a6e0e497deaf9660d000e737893f6a666b60fe68d38db7375b6542d32be`.
  This is specifically the legacy `protocol=shadow` successor. A later
  versioned successor has a distinct envelope identity because its frozen
  successor identity is part of each envelope; it is accepted only when the
  read-only admission boundary rebuilds and matches that exact marker.

## Custody mapping

`v6.2-source-envelope-custody-mapping-v1` binds in exact order every source
entry hash, immutable artifact/history/journal/scorer identity, source
run/manifest/runtime/commit identity, and successor envelope hash. It uses the
same compact canonical serialization and has no digest newline. The mapping
contains no task payloads or journal content. A recovery marker embeds the
mapping plus its hash; admission validates both domains and the full mapping.
