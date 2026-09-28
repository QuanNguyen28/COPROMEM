# Run 012 v5.4 Effect-Path Forensic Audit

This audit is read-only and zero-provider. It preserves run 012, the frozen
v5.3 descriptor, histories, scores, ledger, state, and report unchanged.

## Result: terminal-effect observability remains insufficient

Both CoProMem A trajectories have a durable official score of 1.0. Both
programs syntactically invoke the frozen public terminal callable
`apis.spotify.follow_artist`, and the submitted program receives a native
non-traceback response. However, each invocation occurs inside a `for` loop.
The maintained v5.3 normalizer correctly labels it non-direct: it has no
per-call response observation, no exported call output, and no directly
observed local dataflow edge.

The frozen descriptor was:

`search_artists -> show_artist -> follow_artist`

The normalized public A traces instead contain public discovery calls for
liked songs/albums and following artists, followed by the nested terminal
effect. The first path mismatch is the first discovery call: it is not the
frozen `search_artists` step. Consequently all three frozen descriptor steps
remain absent from the directly observed projection. The projection contains
no callable-schema dataflow edge, so it cannot establish the public
identifier flow required by the terminal effect.

## Classification

This is not evidence against CoProMem and is not a scored comparison result.
It is a **remaining observability limitation** for a rule that requires every
promoted operation, including the terminal effect, to be directly observed.

The terminal call is program-level response-attested, but that is not enough
to weaken `directly observed` into an assumption that a nested iteration ran.
The official score is eligibility evidence only; it cannot be substituted for
public per-operation execution evidence in learned memory.

Therefore the stated precondition for a v5.4 effect-path amendment is not
met. No v5.4 branch, new A/B pair, provider request, or pilot launch is
authorized by this audit.

## Evidence

- Machine-readable decision trace:
  `v5_4_012_effect_path_forensic_audit.json`
- Immutable run report:
  `artifacts/research/official_reme_copromem_pilot/v5_3_engineering_012_tool_schema/final-report.json`

The decision trace stores only hashes, public callable/slot signatures,
sanitized AST control context, and normalized local-binding edges. It excludes
instructions, raw code, values, prompts, responses, scorer state, and memory.
