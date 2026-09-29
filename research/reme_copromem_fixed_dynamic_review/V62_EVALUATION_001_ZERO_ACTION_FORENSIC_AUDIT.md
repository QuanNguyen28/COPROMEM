# Evaluation 001 evidence-contract forensic audit

## Scope and disposition

This is a read-only, zero-provider audit of
`v6_2_task_conditioned_evaluation_001`.  The run, source commit
`6c128a75d71df16fe619de9f178a658287447f3c`, and manifest
`1f0855ee93ebbb8c22c60711cb6c9ccfb52e78cd6b4f1b73f9d525f1da11b316`
remain immutable.  The run is **INFRASTRUCTURE-FAILED** and contributes no
scientific score to any successor.

## Classification: B — validator bug

The sole attempted trajectory was not zero-action:

* ten executor calls were reserved and settled, all with `finish_reason=stop`;
* completion-token counts were 61, 38, 20, 63, 35, 42, 24, 79, 66, and 20;
* all reported zero reasoning tokens and no native tool call;
* the durable action journal has ten `action_submitted` and ten
  `action_applied` records;
* the execution-evidence journal has eleven response-attested rows;
* the scorer journal contains a baseline 0/7 score and a terminal 7/7 score.

The former validator selected every `official_score` journal row and required
exactly one.  It therefore raised `EvidenceContractError: zero-action scorer
evidence is inconsistent` while binding an ordinary nonempty journal.  The
error was at `_scorer_evidence` in
`src/copromem/experiments/reme_copromem/evidence_contract.py`, reached through
the ordinary `bind(...)` call in `execute_trajectory`; the zero-action path was
not eligible because the trajectory had actions and no length-truncated model
response.

The repair labels producer records as `pre_trajectory` and
`post_trajectory`, and the validator binds exactly one `post_trajectory`
record.  It also strengthens the canonical zero-action proof with task/arm/
trial/seed/history/runtime-identity bindings.  A zero-action proof is still
accepted only for one settled 2048-token `length` terminal with no submitted
action, native tool call, or callable telemetry.

## Sanitized durable identities

| Object | SHA-256 |
| --- | --- |
| action/scorer journal | `f86d802578ee46629dffa4c8ed6c71b5f02a199ddec7fc2151f075d732ada346` |
| response-attested journal | `c11443812740d2e2d65a1e2385e006bcb8e64698e9cd7cf888eb31f4ec9a3be9` |
| progress log | `704a12de9a51e0de2bb58bf48c6b457c6f0b692c9aa7ea2fae37af5c857d252e` |
| ledger | `04ec9128be1a39a75e7399c8890ed6e03a91deed7f8e4e7979e21eec12d6bbe5` |

The ledger has 11 reserves and 11 settlements (one carried historical record
plus ten executor calls), with zero unresolved reservations.  No scored
artifact was written and no lifecycle or embedding request was made.

No task text, action program, model response, scorer payload, or secret is
included here.
