# Cycle 23: richer evidence-derived code-monitor proposals

Registered 2026-09-16 after cycles 19--22, before creating proposal inputs,
generating any candidate, or scoring a candidate. This is a **representation
and candidate-construction diagnostic**, not a semantic correctness guarantee,
contract admission, native intervention experiment or main baseline comparison.

## Question and competing explanation

Can a fixed coding model propose an executable code-inspection rule from one
saved failure/repair pair that also distinguishes the other known pair? Compare
with the same proposer given only the successful repaired example. This follows
the failure of the uniform AST-count language; merely adding public name checks
already belongs to the standard control. A model may propose richer relationships
without us manually putting the decisive domain rule into its prompt.

The strongest alternative is a brittle syntactic heuristic or memorized coding
prior. Both pairs are already-inspected build examples; correct predictions do
not establish semantic understanding, a benefit of contrast or held-out transfer.
Native final outcome is the weak predictive target for the **specific saved
continuation**, not a universal annotation of boundary correctness.

## Fixed evidence and inputs

Use the audited cycle-22 corpus and its exact ordering. The two pairs are:

- Old scenario: factual record 10 and repaired record 6.
- New scenario: factual record 12 and repaired record 13.

Each pair must share original episode, boundary index, planner/checkpoint digest
and public presence envelope; its saved native outcomes must be false/true.
Verify the complete cycle-22 audit first. No new source task is selected. All
14 records remain a diagnostic corpus, including repeated origins and programs.

Construct each proposer/runtime input from only the public program and the
sorted names observed present. Require complete queried-name coverage under
the existing cycle-22 definition. Normalize program formatting via `ast.unparse`
and replace every string literal with the same fixed `<string>` marker, removing
comments as a consequence. Preserve names, numeric constants and code structure.
This intentionally loses string-content semantics and avoids forwarding literal
credentials; normalized programs are **never executed as native actions**.
Record source and normalized-input digests separately. Outcomes, source IDs,
native state, logs and provenance remain outside runtime inputs.

Two prompt folds: one trains on the old pair and leaves the new pair out of the
prompt; the other reverses this. This is prompt withholding of known build
evidence, not an untouched test split. Two modes per fold: `contrast` receives
both normalized examples and their saved-continuation outcomes; `success_only`
receives only the positive example. The prompt scaffolding and output language
are otherwise identical. Do not expose omitted programs, labels, hashes or
descriptive task IDs in a success-only request.

## Proposal language and accounting

Request a JSON object containing `source` and `scope_note`. The source defines
`judge(program, present_names)` and optional plain helper functions; it returns
exactly true, false or null. It inspects code with Python `ast`; it must never
execute the submitted target program. The scope note is descriptive and is not
an independently learned/executed applicability policy.

Use three paired request seeds, 61, 62 and 63, per fold/mode: **12 planned model
requests**, one response each, no feedback repair or best-of selection. Keep all
invalid/truncated/rejected outputs. The predeclared model is `qwen/qwen3-coder`,
provider `deepinfra/turbo`, temperature zero, 4,000 completion tokens per request,
no provider fallback, prompt/completion price ceilings USD 0.5/2 per million,
USD 5 total and 36 maximum HTTP attempts. Verify current official endpoint
metadata before paid execution; if unavailable, report the preflight failure
without silently changing the route/model. Use the existing budget-reserving
recorded provider boundary and count every attempt, settlement and ambiguity.

Same request seeds do not guarantee provider determinism. Modes have equal
call/output-token/budget caps but deliberately unequal evidence and prompt
lengths; record actual tokens and do not attribute a difference solely to
contrast without later length/information controls. No retry/recovery policy
or text-memory efficacy comparison is performed at this proposal stage.

Generated Python must run only in a resource-bounded, network-disabled, fresh
container with no host mounts or secrets. Do not run it in the host interpreter.
Use an explicit restricted source policy, fixed builtins and `ast`; reject
imports, private-attribute access, I/O and dynamic execution. Preserve raw
candidate-validation and container process evidence. A syntactic restriction
is not a general security proof; container isolation is an additional boundary.
Freeze the full driver, parser, tests, prompts, inputs, environment image and
protocol before the first paid request. The input preflight alone cannot
authorize execution of an unsafe or unfrozen generated monitor.

## Metrics and decision

Score every safely executable candidate on all 14 normalized runtime inputs.
Record true/false/abstain/error, parse/policy rejection, timeouts, complexity and
cost. Abstention and execution errors are not correct binary predictions. The
four paired source/repair labels are checked explicitly, including both
prompt-exposed and prompt-withheld pairs. Do not select a candidate by the
remaining ten diagnostic outcomes or change its source after seeing them.

Primary construction gate: at least two of three contrast proposals in **each**
fold must be valid and correctly distinguish both factual/repair pairs. If so
KEEP the richer proposal representation for independent falsification; otherwise
REVISE this proposer/representation. Report all success-only counts and paired
differences regardless of the decision. Passing this gate does not establish
contrast superiority, semantic validity, safe recovery or admission. A tie or
better success-only result leaves the need for contrast unsupported.

The standard F821 results remain the name-error control, not a competent manual
semantic verifier. Before any learned-method efficacy claim or native admission,
require a separately frozen manual procedural comparator, anti-shortcut and
scope tests, successful-origin recovery guards, equal-compute/text controls and
untouched-group evaluation. A rule such as `has_while` may fit these records but
is not sufficient scientific evidence. No new native action/scorer, reserved
task, contract-bank write or main-method deployment occurs in this cycle.

## Current execution status

At registration no proposal input preflight, generated monitor, sandbox driver
or paid request has run. Implement and audit the public input construction first,
then validate the isolated runtime and freeze the complete generation protocol.
Keep stage status explicit; a successful input preflight is not the primary
construction result above.
