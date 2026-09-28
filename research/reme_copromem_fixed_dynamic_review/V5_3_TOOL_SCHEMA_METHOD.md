# v5.3 Public Callable-Schema Method Amendment

Status: frozen for zero-provider validation. This amendment does not alter,
replay, or reinterpret engineering runs 009–011.

## Motivation and custody

v5.2 generated paths from public OpenAPI. AppWorld supplies the executor a
separate, public function-calling schema. The two sources can differ in
callable optional fields and in the representation of request and response
fields. A method that learns from executor traces must validate against the
interface that was actually available before execution.

The v5.3 registry is generated only from public AppWorld OpenAPI and public
`function_calling` metadata. It does not read task instructions, task IDs,
trajectories, scorer state, answers, prompts, model output, or execution
results. Each source file is SHA-256 recorded and the canonical registry is
content-addressed.

## Canonical interface

An `operation_signature` contains only application, callable name, canonical
operation, declared public-required parameter names/types, declared optional
parameters present, runtime-context parameters present, and public output-slot
names. Concrete argument values are prohibited.

`access_token` is a frozen runtime-context classification. Local normalizer
bindings named `var_N` are excluded. Callable aliases resolve only through the
registry's public function-name map. All other undeclared fields reject the
candidate path.

For a match, every callable public-required field must be represented. Extra
fields are accepted only when the same frozen callable schema declares them
public optional or runtime context. Types, where available, must equal the
frozen public type. Invocation evidence is separately hashed and never enters
learned schema/procedure text.

## Transactional learning

The task boundary remains `plan -> validate -> commit`.

- Planning uses an isolated clone and stores a sanitized, direct-observation
  projection plus hash-only invocation evidence. A path can contain up to four
  acyclic public operations, allowing a documented lookup chain followed by
  an action; repeated operations fail closed.
- Validation requires one complete ordered registry-supported path, official
  success, observable procedures, and a deterministic eligible winner.
- Commit reconstructs from the frozen pre-state and plan. A rejected plan
  returns a byte-identical semantic state; repeated valid commits reconstruct
  the identical post-state.

Retrieval provenance and its final injected guidance remain subject to the
existing offline byte-for-byte reproduction and tamper checks. Fixed/dynamic
semantics are unchanged: this two-arm engineering protocol exercises only
CoProMem Dynamic; no ReMe service or embedding route is started.

## Retrospective diagnostic boundary

The v5.3 registry was verified and content-addressed before the immutable 011
histories were read. The separate retrospective audit is diagnostic only. Its
recognition result is not v5.3 pilot evidence and does not modify 011.

## Preconditions for a fresh engineering run

A future 012 run may be frozen only after the runtime public schema rebuilds
to exactly the frozen registry hash, all offline validation passes, and a fresh
development A/B pair is selected solely using the frozen registry and public
pre-execution descriptors. A runs fully before B is opened. No `test_normal`,
ReMe, embeddings, retries, or replacement pair is allowed.
