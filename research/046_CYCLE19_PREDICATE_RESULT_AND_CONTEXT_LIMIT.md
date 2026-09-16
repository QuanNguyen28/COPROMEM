# Cycle 19: code-only separators fail the complete effect diagnostic

Recorded 2026-09-16 after the [045 protocol](045_CYCLE19_CODE_PREDICATE_IDENTIFIABILITY_PROTOCOL.md),
implementation, tests, complete screen and exact regeneration. This is an
explicitly post-outcome build diagnostic, not a held-out performance evaluation.
Earlier frozen sources, original documents, branch and HEAD remain unchanged.

## Completed result and decision

The generic miner enumerates **454 single-clause AST-count predicates** from the
four public training examples. **Eighteen** accept both repaired programs and
reject both originals. **None** agrees with all 48 recorded effect/control labels.
The preregistered primary metric is zero; decision **REVISE this bounded
code-only predicate proposal**. No feature expansion, threshold adjustment,
diagnostic-based candidate selection or contract admission follows the result.

All 48 cells are eligible and parseable: ten cycle-13 variant/origin cells,
30 cycle-17 intervention/control cells and eight cycle-18 cells. There are eight
native successes and 40 native failures. Three cells overlap an exact training
origin/boundary/program; the remaining 45 are still previously inspected build
evidence. Four cells share an exact training program regardless of origin. No
duplicates, failures or inconvenient labels were dropped.

| Diagnostic | Result |
|---|---:|
| Uniform node/field-edge threshold clauses enumerated | 454 |
| Consistent with both training pairs | 18 |
| Distinct diagnostic prediction patterns among those clauses | 6 |
| Consistent with every eligible recorded effect/control label | 0 |
| Conflicting-label identical-feature groups | 1 |
| Conflicting-label identical-normalized-AST groups | 1 |
| Model calls / native executions / new API USD | 0 / 0 / 0 |
| Admitted contracts | 0 |

For illustration, the automatically retained `count(While) >= 1` clause accepts
all eight native successes but also 19 native failures. The post-hoc lowest-error
clause in this version space, an assignment-to-constant count threshold, still
accepts ten native failures. It was **not selected as a method**. These are
disagreements with final native outcome, not verified false positives against
ground-truth boundary defects. Neither clause is a semantic correctness check.

Leave-one-source-pair-out construction produces 51 clauses from the old pair,
14 of which also classify the new pair correctly, and 40 from the new pair,
18 of which also classify the old pair correctly. Threshold enumeration depends
on observed training counts, so these directional counts need not equal the
two-pair version space. Both source pairs were already known; this is not
reserved-test transfer and supplies no uncertainty estimate for general efficacy.

## A concrete context counterexample

Two cycle-13 cells execute the **same normalized program**, with AST digest
`3b6e3851403f4a101337fc8401784c933f2dd7fd3214d56f306bc9054058ee9e`,
at different source checkpoints. Removing one collection initializer succeeds
at the formerly failing source and fails at the formerly successful source. The
variant was correctly rejected by cycle 13's requirement to pass **both** origins;
this update does not reverse that decision or turn a rejected variant into a
new retained repair. Eight individual successes here are not eight retained edits.

A separate post-hoc public-code/error diagnostic finds earlier syntactic stores
to `liked_songs` at action indices 10, 11 and 12 in the first public prefix,
none in the second, and a public `NameError` for that name in the second edited
action. No hidden namespace values are read or supplied to the miner. Syntactic
stores alone do not prove an assignment executed; the diagnostic is explicitly
not a sound runtime-availability verifier or learned scope rule.

This exact-code conflict means **no deterministic predicate of submitted code
alone can reproduce both final outcome labels**. It does not mean code checks
are useless: a conservative static guard may legitimately reject a program that
happened to work in one state. Rather, the proposed training target confounds
code, pre-state and downstream behavior. Native task outcome is useful for
effect validation but is not automatically a boundary-correctness annotation.

## Implementation and evidence

The new research prototype keeps proposal generation separate from provenance
and evaluation. It counts every AST node type and direct parent/field/child edge
uniformly, including operator/context nodes. Names, API paths, literal values,
task IDs, instructions, outputs and hidden state do not enter the feature language.
Both comparison directions and every distinct observed threshold are enumerated.
All rejected/accepted clauses, feature vectors, predictions and overlaps are saved.

Clauses are validated JSON interpreted without executing source or evaluating
arbitrary expressions. Invalid syntax/schema produces an explicit abstention.
Serialization/reload predictions are checked. These are genuinely data-selected
**syntactic predicate proposals**, not validated learned stateful contracts.
The representation and search language remain human-defined and disclosed.

Root: `artifacts/research/cycle19_code_predicates`.

- Protocol: `0b1f4db6f690c0c815f84aac33fc722eca28cc7976ee0f40eec5121823073a95`.
- Frozen source snapshot: `d7c355675e27de498b01c8879c96c70336c4cb7b76bb44c9bc9e994785e09522`.
- Full screen and regenerated report: `e70d3ef6d1c0ba9abea12f43c90b4ef3dde8dc4bdb35d3f09df5962f4b053d6b`.
- Separate public-context diagnostic: `ebd0b8aea3349330de8eac92987ab83d1a0ef79c5f21b98392e2dd491a136ea8`.

The existing independent cycle-13, cycle-17 and cycle-18 effect audits are rerun
serially and return their original digests, respectively
`a21610194ac635fbc5c1fdb8cd43ac8417543813c9f557bd07aaa37de2f336e2`,
`c8423053a9a5a3ceb8bbc87a84ee6c19f7768925bde329c13899f4d223c28963`,
and `4c2e4986402e6f8fcb9c591b044edc410ce8f4c1510dcf7346bd1ed0c783b995`.
Full regeneration verifies the new snapshot, public extraction, all inventories,
enumeration, classification, metrics and decision. Regeneration is a software
integrity check, not a second independent scientific sample.

```powershell
$env:PYTHONPATH='src'
python research/scripts/screen_code_predicates.py --audit-only
python research/scripts/diagnose_code_predicate_context.py
python -m pytest -q
```

Thirty-six new language/provenance fixtures pass; the full suite passes 344 tests
before the real screen. One additional post-hoc diagnostic fixture also passes,
explicitly demonstrating that a syntactic assignment can occur in an unexecuted
branch. No old frozen file was edited to add it. All new files pass scoped lint;
the known older frozen-runner FURB192 warning remains unchanged.

## Research consequence and next gate

Retain the two audited local repairs and the complete negative predicate result.
Do not scale the bank, claim a shared contract, or broaden syntax until a rule
fits these labels. Next validate whether a small, **agent-visible read-only
binding envelope** can be obtained at the same saved boundaries without changing
native state/outcome. This must use an ordinary public code action rather than
relabeling harness fingerprints as agent input. Every future arm must receive
the same observation opportunity and pay the same inspection budget.

Context availability would only establish an observation interface. Learning
boundary-specific violations, applicability, safe recovery and admission still
requires new falsifiable gates; generalized collection completeness is not
inferred from a missing-name diagnostic. Strong static/text/equal-compute
controls and group-disjoint transfer remain essential. The autonomous research
goal remains active, with no demonstrated learned-method advantage.

The next bounded experiment is now separately [registered as cycle 20](047_CYCLE20_PUBLIC_BOUNDARY_OBSERVATION_GATE.md).
It has not yet been implemented or executed. Three fixed existing source
checkpoints, two arms and exact public-probe noninterference conditions are
declared before observing any new envelope; no user input or paid API budget is
needed for that local gate.

### Closing verification

The complete suite now passes **345 tests**. A full scoped Ruff run reports only
the already documented frozen engine's style-only FURB192 warning. No native
experiment containers remain running. Both original document hashes, the
research branch and HEAD are reverified unchanged; no commit or push occurred.

The dated selected-scope configured-key scan covers 5,238 files / 37,117,331 bytes,
with zero matches and zero unreadable files, audit
`dc56d50224574b6b00b55f42ed50cefd92bcfc8e33411d97797e5be07ae9a062`.
Its exact scopes are source, tests, research, docs and the cycle-13/17/18/19
stores listed in the saved scan record. It excludes `.env`, Git internals and
unlisted older artifacts. This is a non-atomic exact-current-key scan, not a
claim to detect unrelated or encoded secrets. Prior wider archive/baseline
scans remain separately preserved, not silently replaced by this smaller scope.
