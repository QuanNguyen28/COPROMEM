# v6 engineering 001 ingestion recovery

The preserved manifest `0be83ecc482d00a94fa99868eceeef4eea63d7bc03a9625d2f5c7fc9e6ed7825`
and all A-side evidence remain immutable. The telemetry-to-graph failure was an
integration defect: the graph builder received non-call audit rows although it
correctly accepts only response-attested schema-valid callable records.

The canonical v6 partition now retains non-call audit rows and callable error
rows in a content-addressed audit, passes only response-attested schema-valid
callables to the strict graph builder, and rejects malformed, mismatched, or
unattested callable rows fail-closed. It does not use score, task ID, or arm in
the partition decision and preserves source ordering/indexes.

Recovery is nevertheless ineligible under the frozen method threshold: the two
CoProMem Dynamic A scores are `0.0` and `0.8`, not two official full successes.
No A plan can validate; B stays unopened and no successor is authorized.
