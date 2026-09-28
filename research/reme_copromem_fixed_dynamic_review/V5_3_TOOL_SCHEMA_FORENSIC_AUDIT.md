# v5.3 Tool-Schema Interface Forensic Audit

This is a zero-provider, public-metadata audit. Runs 009–011 remain immutable.

## Finding

The function-calling metadata supplied to the AppWorld executor declares
`user_email` for `apis.venmo.show_transactions` as a **public optional string
field**. It is neither hidden scorer state nor injected runtime context nor a
normalizer artifact. `access_token` is the separately classified public
runtime-context field. Concrete invocation values are excluded from the
registry, path signatures, candidate schemas, and learned guidance.

The old OpenAPI-only path representation was therefore an interface-custody
mismatch: it did not make the actual callable schema the authoritative input
contract. This is an implementation/interface defect, not evidence about a
method's efficacy.

## Evidence

- Frozen callable registry: `appworld_public_tool_schema_registry_v5_3.json`
- Machine-readable interface comparison:
  `v5_3_public_tool_schema_interface_audit.json`
- Post-freeze, read-only 011 diagnostic:
  `v5_3_011_retrospective_tool_schema_audit.json`

The interface audit records every OpenAPI/function discrepancy using only
operation names, parameter names/types, source hashes, and classifications.
The 011 diagnostic reads the frozen registry first and emits only artifact and
history hashes plus public operation/slot signatures. It recognizes both
immutable successful histories as complete public callable paths, but this is
retrospective diagnostic evidence only.

## Guardrails

The implementation rejects missing required fields, undeclared fields,
type mismatches, concrete values at the signature boundary, registry tampering,
and a live public schema whose rebuilt registry hash differs from the frozen
one. Strict v5, v5.1, and v5.2 policies retain their previous code paths and
tests.
