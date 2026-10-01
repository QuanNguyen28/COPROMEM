# ReasoningBank AppWorld retrieval provenance v4

This is an infrastructure integrity boundary for the controlled
ReasoningBank-AppWorld port. It does not change upstream ReasoningBank
retrieval: query embedding, cosine top-1 selection, and append-order tie
breaking remain unchanged.

## One identity and one rendered value

Before dispatch, a `RetrievalIdentity` is frozen with trajectory, task, arm,
trial, seed, benchmark, manifest byte SHA-256, runtime-identity file SHA-256,
and callable-registry SHA-256. The same validated value is used by retrieval
materialization, the post-`prompt_messages` prompt seal, scored-artifact
verification, the Dynamic checkpoint, and restart verification. Missing,
malformed, or unequal fields fail closed before the executor call.

Raw selected memory is retained in a separate content-addressed object. The
only value delivered to the executor is the output of the sole authoritative
`render_retrieval_guidance` function. Provenance stores both UTF-8 byte hashes,
the generic executor memory-slot hash, and the exact initial model-message hash.
Thus lifecycle output, provenance output, callback output, prompt content, and
offline replay must be byte-identical. Empty rendered guidance produces no slot
and is byte-identical to the corresponding No Memory prompt; it never requests
a ReMe fallback.

## Prompt seal and restart state machine

After `prompt_messages` and before `call_llm`, the runner atomically writes and
fsyncs an immutable prompt binding, reloads it, and atomically records its
hash-bound reference in the retrieval record. Repeating the same seal is
idempotent. A partial binding file is completed only when its complete immutable
contents match; unreadable, missing, or conflicting files fail closed. A scored
artifact may enter the Dynamic lifecycle only after the seal, execution evidence,
and artifact identity have all verified.

The Dynamic checkpoint manager remains the authority for post-score intent,
settlement interval, snapshot, verifier dump, completion marker, and restart.
It may not update after artifact finalization fails and never replays a valid
completed update.

## Compatibility

The historical private CoProMem renderer import is a behavior-free re-export
shim to the one generic executor memory-slot helper. It contains no template or
ReasoningBank rendering logic. Historical retrieval data remains audit-only;
new executions require v4 identity and prompt-seal evidence.
