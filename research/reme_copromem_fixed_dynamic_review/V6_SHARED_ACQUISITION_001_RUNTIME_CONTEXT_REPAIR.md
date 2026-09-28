# V6 Shared Acquisition 001: Runtime-Context Classifier Repair

`v6_shared_acquisition_001` completed all 24 shared acquisition trajectories
before bank construction. Its immutable dispatcher journals contain three
HTTP-200 calls marked `unknown_undeclared_field` solely because the original
recorder did not consume the already frozen registry-wide
`normalization.runtime_context_fields = ["access_token"]` rule.

This is an implementation defect in evidence classification, not a trajectory,
scorer, model, or method outcome. The registry already declares
`access_token` to be runtime context; it is not a public learned argument.

The repair has two deliberately narrow effects:

1. New dispatcher records classify every frozen global runtime-context field
   as context, while preserving it outside public operation signatures.
2. A zero-provider reconstruction can reclassify a legacy record only when it
   has no missing public requirements and its complete unknown-field set is a
   subset of the frozen runtime-context set. The original append-only record
   and its hash are not modified. Every such reclassification is included in
   the derived bank audit.

Any other unknown field, a missing public field, a registry/version mismatch,
or an evidence-hash mismatch remains fail-closed. Failed HTTP calls remain
negative evidence and cannot be promoted. Construction outputs are written to
a separately named recovery directory and point to the immutable source
manifest and shared-pool hashes. No acquisition, provider, scorer, embedding,
or decomposition request is replayed by this repair.
