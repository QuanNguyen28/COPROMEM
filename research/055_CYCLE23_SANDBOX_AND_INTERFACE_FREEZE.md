# Cycle 23 sandbox result and pre-generation interface clarification

Recorded 2026-09-16 before any cycle-23 model request or candidate score.
[Protocol 053](053_CYCLE23_MONITOR_PROPOSAL_PROTOCOL.md) remains unchanged.

## Constructed runtime gate

All ten constructed fixtures pass twice in separate containers: AST inspection,
public names, abstention, nonboolean rejection, runtime error, private-attribute
rejection, import rejection, inaccessible AST module globals, immutable name
inputs and CPU timeout. Twenty sandbox processes execute, but zero native
benchmark actions/scorers and zero model calls. These are engineering fixtures,
not learned rules or evidence of task improvement.

Store: `artifacts/research/cycle23_monitor_sandbox_preflight`.
Report: `d2061cd58e5acc90e5354af9d3ad3ca4cf234218ee1a1d9a0c26ee2b935948ed`.
Protocol: `c5afe0d2944420651b539c150f6135a15aabd3c647d1850fb106e2475fbc5d4d`.
Source snapshot: `922156f7ed522be10ba8a0a649d799a219f5a708503a04c679ef74ed6d5eec6f`.

Each container uses the pinned existing Linux image, an overridden entrypoint
that clears environment variables, an unprivileged UID, no host mounts, no
network, a read-only root, dropped capabilities, no-new-privileges, CPU/memory/
process limits and a host wall timeout. The image has no implicit volumes.
Proposed source is parsed on the host but executed only in the container.
Only normalized public code and present-name data reach `judge`; the target
program itself is never executed. The AST interface exposes node classes and
listed inspection utilities, not arbitrary module globals. Source validation
does not constitute a general sandbox-security proof.

Complete raw Docker argv/stdin/stdout/stderr/status are retained. CPU timeout,
invalid results and runtime errors are not verdicts. Interrupted unresolved
attempts cannot be silently restarted. Cleanup verifies the exact created
container name and ownership/input labels before termination. Twenty-eight
focused host-side fixtures pass without executing proposed code on the host.

## Prompt clarification before any generation

The input preflight prepared **base requests**, before the runtime API existed.
The final requests append an identical, domain-neutral interface specification
to both modes' system prompt. It makes the actual restrictions explicit:
function signatures, no leading-underscore names, annotations/defaults/decorators/
nested functions, exact builtin and AST utility availability, tuple-valued
present names, strict JSON, source/complexity limits and resource bounds.
This prevents rejection for an undocumented runtime rule from masquerading as
failure of evidence-based induction.

The base requests and their snapshots remain preserved; the final freeze records
both base and final request digests. Example contents, source pairs, folds,
labels, seeds, model, route, token/monetary caps and primary metric do not change.
No domain-specific procedural rule, candidate feedback or extra example is added.
This is an explicit pre-generation implementation clarification, not an
after-results prompt improvement.

## Provider and generation handling

Use the official endpoint metadata to verify the registered tag, model, supported
parameters, context capacity and token price ceilings immediately before paid
collection. Preserve its raw numeric status and uptime without assigning an
undocumented meaning to a status code. The provider may be degraded; metadata
listing is not a guarantee that a completion succeeds. The registered client
allows only the selected route, reserves cost before attempts and never falls
back to another provider.

If a logical request fails after its bounded transport attempts, preserve the
failure, stop further paid collection in that invocation, and mark all remaining
slots unattempted in the report. Do not call an incomplete-provider diagnostic
a rejection of the learning mechanism. Every planned slot remains in the
denominator. Never automatically restart an ambiguous prior request. No syntax
repair, prompt retry or best-of selection is added for invalid candidates.

KEEP the constructed runtime for this restricted diagnostic. The primary
candidate-construction decision remains pending until the complete registered
generation/scoring report. The goal remains active; no contract admission or
learned-method advantage is established.
