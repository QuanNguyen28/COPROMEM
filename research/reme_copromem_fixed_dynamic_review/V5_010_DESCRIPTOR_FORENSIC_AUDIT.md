# v5.1 run 010 descriptor forensic audit

This is a zero-provider reconstruction from immutable 010 artifacts. No task
was replayed and no benchmark payload, scorer state, or provider response is
included here.

## Decision

Classification: **descriptor-generation bug plus mandatory-conjunction design
flaw**. Both successful CoProMem trajectories completed, but the frozen
descriptor treated an incorrect two-operation public API hypothesis as a
mandatory conjunction. The observed workflow used a different public read
operation and a different public reminder/write operation, with public
relationship/date/filtering dependencies in between.

The first mismatch in both traces was the descriptor-required read operation:
no normalized observed event had its operation-and-slot signature. The second
descriptor-required write operation likewise had no exact canonical match.
These are not aliases normalized by the current identity-only matcher.

## Sanitized operation table

| Frozen required role | Result | Evidence category |
| --- | --- | --- |
| request-read | missing exact canonical operation/slots | alternative supported read path observed |
| reminder-write | missing exact canonical operation/slots | alternative supported write path observed |
| authentication, documentation, completion | non-required helpers | public helper/internal evidence |
| relationship/date/filtering | not represented by frozen descriptor | workflow dependency/exploration evidence |

The offline reconstruction reproduced `v5_1_descriptor_coverage_incomplete`.
No hidden scorer or task-specific rule is needed to explain it.

## Required amendment

A v5.2 method must freeze public *alternative dependency paths*, not a union
or guessed conjunction of APIs. A projected procedure may commit only when one
complete public path is directly observed, all its dependencies are satisfied,
and its content-addressed signature is shared by a compatible B query. Strict
v5 and v5.1 remain unchanged.
