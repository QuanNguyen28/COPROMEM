# v5.2 public alternative-path registry

Status: frozen zero-provider infrastructure.  Policy identifier:
`observable_supported_path_v5_2`.

## Source and custody

`appworld_public_path_registry_v5_2.json` was built only from the eleven
public AppWorld OpenAPI documents under `data/api_docs/openapi`.  The generator
uses operation IDs, HTTP methods, endpoint templates, declared parameter names,
and declared successful-response property names.  It does not accept task IDs,
instructions, histories, scorer output, model output, entities, dates, user
data, or task parameters.  The registry hash is
`b8214dc7079cd05f28c098ea1cb108508eb0aaed818ad8f58aba224f7a6b4b3b`.

The registry models a public *capability graph*.  A schema-flow edge means a
read operation publicly declares an output slot that a later write operation
publicly declares as an input.  It is not a claim that the two operations are
semantically interchangeable or that the path solves any task.

## Registry representation

- Operations carry a canonical `apis.<app>.<operation>` name, app ownership,
  HTTP method, read/write distinction, required and optional input slots, and
  declared response slots.
- Alternative groups enumerate public schema-compatible producers for a
  consumer input.  Their status is deliberately
  `schema_compatible_not_semantically_equivalent`; v5.2 never treats a lexical
  or outcome-derived similarity as an alias.
- Dependency edges are only public read-to-write schema flows.  This prevents
  generic CRUD cycles from being promoted as procedures.
- The sole task-independent runtime normalisation omits the framework's local
  `var_N` bindings and `access_token` infrastructure argument.  It then checks
  all remaining public input names against the frozen OpenAPI signature and
  derives response slots from that same frozen signature.  No response value is
  retained.
- Optional parameters are not required observations.  Every selected path node
  is mandatory; nodes absent from the selected path are optional rather than a
  mandatory union of all APIs.

## Transactional v5.2 rule

Before execution, a task descriptor must name one ordered path from the frozen
registry.  At a task boundary, the planner retains only direct public operation
and slot evidence for that path, removes all parameters and values, and
validates that each non-public input is supplied by an earlier selected public
output.  It commits exactly one deterministic full-success winner only after
that validation.  Rejection returns the byte-identical pre-state.  The stored
projection and registry hash make offline reconstruction possible.

Strict v5 and v5.1 retain their existing validators unchanged.  v5.2 is a
separately versioned method amendment, not a reinterpretation of old runs.

## Retrospective diagnostic only

After freezing the registry, `v5_2_registry_retrospective_audit.json` read
immutable 009/010 evidence and found one registered public path in each.  This
post-freeze diagnostic is not pilot evidence, did not alter either run, and was
not used to create registry metadata or select future task IDs.

## Limits

OpenAPI schemas do not encode task intent, scorer semantics, or every
application-level constraint.  Consequently a v5.2 path is necessary public
structural support for a learned procedure, not proof of task correctness or
transfer.  Any future A-to-B engineering run must freeze its pair and its one
registry path before execution, preserve values outside memory, and enforce
the existing transaction/retrieval-provenance gates.
