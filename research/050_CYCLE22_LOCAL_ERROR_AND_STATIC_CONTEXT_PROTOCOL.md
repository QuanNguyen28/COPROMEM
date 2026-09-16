# Cycle 22: local-error labels and a public-context static checker component

Registered 2026-09-16 after cycle 21's complete noninterference audit, before
constructing or running the following checker comparison. This is a zero-model,
zero-new-native-execution offline development diagnostic, not a main-method
comparison, a strong semantic-verifier reproduction or a held-out result.

## Hypothesis and competing explanation

Public entry-context information can reduce a standard undefined-name checker's
spurious warnings on code that legitimately uses existing bindings, while
retaining detection of observed missing-name errors. The strongest alternative
is that the checker remains insufficient: lexical undefined names are not a
sound analysis of execution paths, conditional initialization, exception flow,
consumer correctness or final task success. No learned-memory advantage follows
from a standard checker benefiting from context.

## Fixed complete sample and provenance

Use all ten cycle-13 variant/origin cells, all three factual target actions at
the cycle-21 boundaries, and cycle-18B's passing new-task edited action: **14
action/checkpoint records**. Keep duplicates and both original outcomes. No
record is selected or dropped based on checker output. Bind every action to its
audited source execution and the matching cycle-21 pre-query checkpoint.

The cycle-21 envelope supplies only actually observed name-presence booleans.
Reject a name as unavailable only when that exact name was queried and marked
absent; unqueried names remain unknown. Do not infer their absence from omission
or fill them using hidden namespace data. Query coverage limitations must remain
explicit. Exact same-origin/context binding, including the original planner and
pre-action supported-state identity, must be verified before reusing an envelope.

The binary local label is whether the **actual target action's public output**
reports an uncaught `NameError`, with both a native execution-failure prefix and
a recognizable exception line. Preserve the error name and classify other,
ambiguous or missing outputs separately. Do not use final native task success as
the local ground truth. Report final success only as a separately labeled audit
column to demonstrate the difference, never as a constructor feature.

## Two standard static configurations, no learned arm yet

Inspect and record the installed Ruff CLI version and its local official rule
description for F821. Run the **unchanged installed checker** using JSON output,
F821 only, an explicit Python target matching the native worker, and isolated
configuration so repository lint options cannot silently change the comparison.
Record executable/version, exact argv, input digest, raw stdout/stderr, exit
status and parsed findings. Do not substitute a locally rewritten F821 rule.

Configuration A analyzes the target action with only the shared public `apis`
name declared. Configuration B additionally declares the names marked present
in the exact bound public envelope. Both use analysis-only `name = None` stubs,
never execute those stubs, never inject them into native programs or prompts,
and never claim the real values are None. Keep stubs outside reported original
line positions by recording the offset. Select no rules or thresholds after
seeing the first report.

Neither condition may inspect evaluator bodies, namespace fingerprints, actual
binding values or task instructions. The source action itself and the public
presence envelope are the complete inputs. The fixed stub for `apis` is shared
framework infrastructure, not learned domain knowledge. Quarantined unknown
coverage or checker/parse errors remain reported rather than counted as success.

## Metrics and decision

Report all 28 checker/action configurations, all F821 diagnostics, targeted-name
coverage, local label/ambiguity, confusion counts, disagreements between the
two configurations and no-context versus context false-warning changes. These
are correlated development cases, not independent trials or statistical evidence
of general performance. Multiple undefined names in one action remain one
action-level warning, with individual names preserved.

Primary component gate: B must strictly reduce false warnings among the
unambiguously labeled covered actions without losing any true detected
NameError action relative to A, with all 14 records accounted for. If so **KEEP
the context-aware F821 component for later controls**; otherwise **REVISE**.
Also report every unknown/uncovered and non-NameError failure separately; neither
configuration is promoted as a sound or strong semantic contract verifier.

Freeze the new adapter, rule/version evidence, public inputs and full manifest
before executing real checker cells. Tests must cover source/envelope identity,
unknown versus absent, builtin and provided-name treatment, stub nonexecution,
line offsets, exit-status interpretation, malformed JSON/findings, complete
denominator and native-success/local-error separation. Regenerate the corpus,
all invocations and metrics after the run. Preserve failures and raw outputs.

No bank admission, recovery execution, new model call, reserved task or paid API
cycle is authorized by this gate. A later learned-method experiment still needs
explicit local semantics and scope, a strong manual semantic verifier, matched
recovery/text/equal-compute controls and group-disjoint transfer. The full
research objective remains open.
