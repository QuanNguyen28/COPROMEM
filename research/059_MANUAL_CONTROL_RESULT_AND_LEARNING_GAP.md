# Manual control result: known residual failures do not establish a learning gap

Recorded 2026-09-16 on `codex/copromem-research-loop`, HEAD
`18025102c010e85f26b0b3fb1144a1cb684b587e`.

**Decision: REVISE remains.** The implemented manual pagination control flags
all four native failures left clear by B. There is therefore no demonstrated
learning-specific residual failure in this fourteen-record diagnostic. Adding
the manual consumer rule also flags one native success, reinforcing the
difference between a procedural risk and the benefit of intervening now.

This follows the [bounded diagnostic specification](058_POST_GATE_MANUAL_CONTROL_DIAGNOSTIC.md).
The rules are human-written AFTER inspection of these programs and outcomes.
Results are post-hoc development associations, not held-out accuracy, learned
discovery, recovery efficacy, or evidence that no future learned rule can help.
The strict Cycle-22 result and its original primary metric remain unchanged.

## Complete results

`Pattern` means the supported pagination idiom is present, not that the program
is correct. `Unknown` means unsupported or insufficiently observed context;
the combined control still warns if the previously recorded B warning applies.
The consumer warning is first-artist selection feeding a follow call. No target
program executes in this diagnostic.

| Frozen row | B | Pagination | Consumer risk | B + manual | Saved native |
|---:|---|---|---|---|---|
| 0 | Clear | Empty collection, no producer | None | Warn | Fail |
| 1 | Clear | Empty collection, no producer | None | Warn | Fail |
| 2 | Warn | Pattern | None | Warn | Fail |
| 3 | Warn | Pattern | None | Warn | Fail |
| 4 | Clear | Pattern; existing collector value unknown | None | No detected risk | Pass |
| 5 | Warn | Unknown collector initialization | None | Warn | Fail |
| 6 | Clear | Pattern | None | No detected risk | Pass |
| 7 | Clear | Pattern | None | No detected risk | Pass |
| 8 | Warn | Unknown initial page | None | Warn | Fail |
| 9 | Warn | Unknown initial page | None | Warn | Fail |
| 10 | Clear | Single page for full-set obligation | None | Warn | Fail |
| 11 | Clear | Pattern | None | No detected risk | Pass |
| 12 | Clear | Single page for full-set obligation | First artist only | Warn | Fail |
| 13 | Clear | Pattern | First artist only | Warn | Pass |

Row 11's actual source already has pagination; its saved task passes. It must
not be described as an unpaginated failing-source control. Row 13's native
success remains true; the consumer finding does not change its label.

| Association with saved native outcome | B | B + pagination facet | B + full manual control |
|---|---:|---:|---:|
| Warn on native failure | 5 | 9 | 9 |
| Warn on native success | 0 | 0 | 1 |
| No detected risk on native failure | 4 | 0 | 0 |
| No detected risk on native success | 5 | 5 | 4 |
| Combined abstentions | 0 | 0 | 0 |

The pagination facet is reported to separate findings within this one manual
reference, not selected post hoc as a winning method. The full control was
specified before this run and its extra warning is retained.

Relative to B, the full control adds warnings on four saved failures (0, 1, 10,
12) and one saved success (13), with nine unchanged warning decisions. If native
failure were used as the binary prediction target, these would be four helpful
and one adverse classification changes. That target is not universal procedural
correctness. **Task-level beneficial and harmful flips are both unmeasured**:
the checker did not select or execute a repair. No learned-arm comparison exists.

## What the control actually establishes

The manual reference connects the required public API call to its response,
collector and subsequent consumer. Recognized patterns check the actual page
index, accumulation destination, statement order and empty-response exit. Tests
ensure that no advancement, disconnected collection, extra early exits and
unsupported update forms cannot pass solely because a loop exists.

It is deliberately NOT a general Python analyser. It recognizes two explicit
pagination idioms and abstains on other forms; task scope uses manually written
public-language/API associations. Its first-artist dataflow check is syntactic,
not a full alias/control-flow proof. Additional code paths could cover artists,
or an artist could already be followed. It does not establish collection types,
database cardinality, API stability, short-page terminal semantics or all
downstream effects. A recognized short-page idiom carries an explicit unproved
API-assumption warning. No authoring-effort reduction has been measured.

These limitations prevent calling it a validated cross-domain strong baseline.
It is nevertheless an implemented, transparent counterexample to the argument
that the four observed F821 misses by themselves require learned verification.

## Corrected information boundary

The existing targeted redactor now materializes all fourteen public views.
All fourteen literal credential occurrences are replaced with opaque markers;
semantic literals, public task requirements, API documentation and public
present/absent names are retained. Unknown credential expressions are withheld.
This bounded literal/alias handling is not a general secret detector.

On the actual record-13 genre mutation used in the earlier information-limit
finding, the corrected views are now distinct:

- Original view: `1d1db3ec9336cf7ba524a78e8e40eaa329f68376e266aedf559fae979d928993`.
- Altered view: `af1f7899d474a8fb9eb1d51f56e59928557a316eba0780ee31fa57bc4abd8199`.

The altered view also adds the expected manual genre-mismatch warning. This is
a constructed source mutation, never a native execution or task-level flip.
The original all-string-redaction collision remains preserved as negative
evidence. The new view is NOT wired into the paused monitor-generation runtime;
its old twelve-request experiment must not be resumed unchanged.

## Leakage, reproducibility, calls and cost

- Decision function input has exactly version, redacted program, task instruction,
  public presence and public API documentation. No record ID, native score,
  runtime error output, hidden state or evaluator body is supplied. Labels and
  record IDs are attached by the runner only after the public-only decision.
- Human rule development used known-build outcomes. That is disclosed development
  exposure, not evidence of blind evaluation. No reserved scenario is read.
- Inputs use a common seven-API catalog derived from the known programs, without
  outcome-based API selection. It is not a held-out catalog-construction policy.
- All source-case/view hashes, original checker dependencies, public documentation
  hashes and copied-view deterministic results verify. Fourteen decisions are
  inspected twice, plus one constructed mutation: 29 manual inspections total.
- Full suite: **464 tests pass**. Scoped new-code lint passes. Existing frozen
  files, branch/HEAD and both original research-document hashes are unchanged.
- **0 new model calls, 0 native executions, 0 new Ruff experiment invocations,
  0 sandbox runs, USD 0 API cost.** Local compute and human rule-writing effort
  are not claimed free; no latency measurement was collected for this run.
- Paid totals remain USD 2.85687245 settled / 2.85793295 charged-reserved.

Stores and reproducible evidence:

| Artifact | Digest |
|---|---|
| Corrected public-input report | `b0310aa011240150c6efa344d575ae24579681072b44b87a39631233c436f74d` |
| Public-input source snapshot | `83374e7d45bf96b2eb0907bfb02c1979f0c9334b228d4f9b150ba54de8ba1b3f` |
| Manual-control report | `f0f6d56e74663d66cf6c297f889c63efdf6b632a049c5f403f2fd5e48af7ba71` |
| Manual-control source/specification snapshot | `1b606539e732e146cb4742df09537f610bffe3f65fe35b1a522ba4027306b44b` |

Raw reports/views are in `artifacts/research/post22_public_semantic_view` and
`artifacts/research/post22_manual_coverage_control`. The append-only stores retain
the frozen source text and complete per-record decisions. Existing native and
Ruff evidence is reused, not recollected.

A dated exact configured-API-key scan of the new source/test/specification/result
files, both new stores and root files (excluding `.env`) scanned 31 files /
227,352 bytes with zero matches and zero unreadable paths. Audit record:
`1543d771b444da9aad6eed066f503e77853bb842ef80ef856639328f5f56a515`.
It neither persists the key nor claims to detect encoded/unknown secrets; it
describes those explicit scopes at scan time, before this audit paragraph.

## Consequence for the next research action

Do not scale or claim a learned-verifier quality gap from these cases. A useful
next learning test needs a concrete distinction beyond this manual coverage
logic, plus an actual induced candidate and the shared repair branches required
by the strict decision. The remaining scientifically relevant question is
whether to intervene when a risk exists, given the repair's benefit, harm and
cost—not whether native success certifies a universally correct procedure.

That is a candidate repair-selection reformulation, not an established novel or
superior pivot. It must demonstrate incremental value over the same-information
manual activation policy and always-repair/no-op controls. If no observable
learning-specific distinction can be specified, pivot away from verifier-quality
claims rather than generate known-build predicates or build another platform.
No candidate, admission, held-out selection, paid request, commit or push occurs.
