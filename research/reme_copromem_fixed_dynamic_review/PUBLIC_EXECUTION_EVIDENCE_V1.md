# Public execution evidence v1

## Scope

This is an infrastructure-only amendment for AppWorld task-boundary evidence.
It does not change prompts, model routes, memory selection, the scorer, or the
strict v5/v5.1/v5.2/v5.3 decision predicates.  It replaces only the former
source-structure approximation of *whether a public call ran* with a native
dispatcher observation.

## Source audit

The pinned native runtime is AppWorld `0.1.3.post1`.  The audit found no
official callback, transaction hook, or response-attested per-call trace API.
It did find two relevant official components:

| Component | Evidence | Consequence |
|---|---|---|
| `ApiCollection._wrap_api_request` | `collections/apis.py`, SHA-256 `597aa608dd2447b8e77805490baa0289d549fb79c6d3d2b382637713e5a4eefe` | Every exposed `apis.<app>.<callable>` function invokes `Requester.request`. |
| `Requester._request` | `requester.py`, SHA-256 `9660a3ab9bf222c64d4f265a6551d375368faf652b783e3ab0996389e5137bec` | Single native request dispatch returns the response object before public JSON conversion. |
| `Requester.request_tracker` | same requester source | Official `api_calls.jsonl` records request method/path/data, but has no response status/body hook. |
| `AppWorld.execute` and `save_logs` | `environment.py`, SHA-256 `ad650588158727c4ebe72a080638ec0174c33af8a8b9e9b81f3d9bfda55d3fd9` | Executes the submitted program once and writes the request tracker after execution; it is not a per-call observer. |

Therefore v1 wraps the narrowest shared public dispatch, `Requester._request`,
inside the JSON-lines worker.  It does **not** parse Python source, inspect
scorer state, access task databases, or inspect benchmark answers.

## Native filesystem diagnosis and repair

The first native fixture did not fail because of Windows-to-WSL conversion or
a missing parent.  The explicit journal path resolved under `/mnt/e`, its
parent was created, and the zero-content open/flush/fsync/read-back preflight
passed.  The first event then failed at the **write** operation with Python
`UnsupportedOperation` (no OS errno).  The pinned AppWorld safety guard
temporarily replaces both `builtins.open` and `io.open` with a read-only
function while submitted agent code executes.  `Path.open` therefore failed
inside the dispatcher wrapper even though the E-backed filesystem was healthy.

The recorder now retains only value-redacted event metadata in an action-local
buffer while the native program runs.  The worker restores the original
dispatcher and AppWorld's file functions, then appends, flushes, and fsyncs the
ordered records before acknowledging that action.  This is not an in-memory
fallback: a journal preflight and every completed action require durable E-backed
storage, otherwise the worker fails before acknowledging the action.

The boundary accepts only an explicit absolute E-drive Windows path or its
`/mnt/e/...` WSL form.  It never derives a journal from the worker CWD, creates
and validates the parent before AppWorld construction, exports only a path
identity digest in startup telemetry, and rejects malformed/incomplete records
on restart.

## Persisted event contract

One append-only, fsynced event is written for each dispatcher entry after its
containing submitted program has returned.  It has a parent submitted-program
identifier and an action-local monotonic index.  It contains only:

- the frozen callable-registry SHA-256;
- canonical application/callable/public-field names and declared types;
- hashes of invocation values, never values;
- a success/status/error class plus value-free response shape/hash;
- an event hash.

Unknown callables, unknown fields, missing required public fields, failed
responses, registry mismatches, malformed writes, duplicate indices, and
tampered records make the evidence projection invalid.  They never become a
learned procedure.  Telemetry records are not placed in an executor prompt or
learned memory.

## Learning boundary

`observable_tool_schema_execution_evidence_v1` applies the existing v5.3
callable-schema path predicate to response-attested dispatcher events.  Each
learned event derives its operation and slot names from the frozen public
registry; it has no concrete argument value, task instruction, response body,
or scorer information.  Existing strict-v5, v5.1, v5.2, and v5.3 policies keep
their existing source-history behavior unchanged.

## Equivalence and restart claims

The recorder returns the native response unmodified.  It queues evidence only
after the native dispatcher returns or raises, then writes after native program
execution completes, so enabling it cannot modify public API arguments,
response values, task state, or scoring.  Each event is fsynced before the
worker returns the action result; the runner therefore sees durable evidence
before it can request another model completion.  A restart verifies event
hashes and parent/index uniqueness rather than silently accepting an interrupted
or conflicting write.

The committed tests cover explicit path conversion, missing parents, unrelated
worker CWDs, invalid destinations, interrupted writes, direct calls, loops, a
non-executed condition, helper calls, exceptions, failure, registry mismatch,
duplicate/tamper, and value-redaction cases.  The native zero-model fixture
compares telemetry-off/on public output, the final native-state hash, official
score, public prompt/tool-interface hash, and an exact five-call nested order.
