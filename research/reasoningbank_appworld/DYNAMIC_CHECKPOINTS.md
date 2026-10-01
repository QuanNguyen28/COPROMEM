# ReasoningBank Dynamic checkpoint boundary

The controlled AppWorld port uses the pinned upstream online lifecycle: a
self-judge labels the just-completed trajectory, the corresponding upstream
success/failure extraction prompt is sent at temperature 1.0, and the new
experience is appended.  AppWorld's official score is never supplied to that
lifecycle.

## Durable order

The executor first writes and validates a scored artifact and its execution-
evidence/scorer bindings.  The Dynamic boundary then writes an fsynced intent,
performs the one permitted judge/extract/embed/append update, writes an
fsynced E-backed bank snapshot, restores it twice in clean verifier instances,
and only then writes an fsynced completion marker.  Intent and marker bind the
trajectory, scorer artifact, evidence journal, retrieval record, pre/post
semantic hashes, predecessor marker, snapshot/verifier hashes, and exactly the
provider settlements created between this intent and the next intent.

## Restart state machine

- no intent/marker/snapshot: the next frozen update may start;
- valid intent + snapshot + marker: restore the verified snapshot and skip it;
- intent without marker, snapshot without marker, marker without snapshot,
  noncontiguous order, or any hash/settlement mismatch: fail closed.

No restart reissues a provider-backed lifecycle operation.  The fixed bank has
no checkpoint namespace and is rejected if it enters the Dynamic boundary.

## Strict executor callback

The generic executor keeps legacy best-effort callbacks for older callers.
The ReasoningBank Dynamic runner passes `post_score_update_strict=True`: a
post-score failure is durably logged and propagated only after the scored
artifact remains intact.  The runner must stop before selecting another
trajectory; it may reconcile but never replay the scored trajectory or an
ambiguous lifecycle call.
