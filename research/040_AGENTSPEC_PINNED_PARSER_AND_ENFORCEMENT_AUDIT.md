# AgentSpec: pinned source and bounded parser/interpreter audit

Recorded 2026-09-16 during the independently running cycle-17 effect experiment.
This baseline work changes no CoProCon collector, native evaluator, frozen effect
protocol or upstream baseline file. No model, interactive approval, shell tool,
email service or embodied action is invoked.

## Provenance and inspected scope

The [official repository](https://github.com/haoyuwang99/AgentSpec) is pinned at
`e6fa3902e2cfb9681f454b355691b771f70543f8`, under
`artifacts/research/baseline_sources/AgentSpec`. Its sparse worktree contains only
root documentation/dependency metadata, direct Python implementation files,
generated parser/grammar files and manual rule sources. Benchmark/result payloads,
LLM-generated rule datasets, bytecode and the Java tool archive are not materialized
or used. The upstream worktree is clean; no fixes are made inside it.

The current implementation has distinct components: `Rule` parses and selects
events; the interpreter evaluates predicate names through a Python registry;
enforcement dispatch selects stop/skip/no-op/manual inspection/reflection; the
LangChain executor intercepts actions and applies rules. This reinforces that
runtime executable checking and corrective routing are strong existing controls,
not new contributions of CoProCon. LLM rule generation and the separate Apollo
translation path were not reproduced by this audit.

## Environment and what actually executed

The generated lexer/parser and `rule.py` are imported unchanged. The upstream
`CustomErrorListener` and `RuleInterpreter` class bodies are compiled unchanged
from their source ASTs, with dependency-heavy module imports and the demonstration
entry point bypassed. The fixture supplies type placeholders and an empty predicate
registry; it exercises literal-boolean interpretation, not actual domain predicates
or recovery actions. Enforcement support is inspected from the actual dispatch
mapping, not executed on a tool.

The reused isolated image is
`sha256:b5f9aaedde041e30fc4ff795ab46d47849cfc72701b9ffc8c8983fdefe36fcf6`:
Python 3.12.14, Pydantic 1.10.26. The separately hash-pinned official PyPI pure-Python
ANTLR wheel is 4.13.0, satisfying the source's `==4.13` requirement. Generated source
identifies ANTLR 4.13.2. The fixture runs read-only, non-root, with no network,
no host environment credentials and no task database. This is **not** a fully
resolved/native AgentSpec LangChain installation or its historical paper environment.

Wheel SHA-256:
`53e6e208cf4a1ad53fb8b1b4467b756375a4f827331e290618aedcf481cb1d5c`.
Interpreter source SHA-256 after UTF-8 text loading:
`ebf69b5e22416e8c410a74a37c7269984746764123223c61b1d7ae1ca37d212f`.

## Eighteen authored probes, repeated identically

These are observed constructed-input behaviors, **not eighteen correctness wins**.
All raw stdout/stderr, including parser error messages and exception types, is saved.

| Inspected behavior | Observation | Adaptation implication |
|---|---|---|
| Valid single rule and supported reflection spelling | Parse without syntax errors | Establishes a native parser/Rule path, not predicate efficacy |
| Two rules passed to one `Rule.from_text` call | Result describes the last rule | Build a deliberate one-rule/list interface; do not silently lose earlier rules |
| `any` event | Grammar reports an error but `Rule.from_text` still returns an object | Construction alone is not validation; preserve interpreter error handling |
| README custom predicate before documented grammar/registry extension | Parser error | The README explicitly requires extension; an unextended example is not an installed predicate |
| README `llm_self_examine` versus implementation `llm_self_reflect` | First spelling errors, second parses | Pin version and actual supported DSL vocabulary |
| Exact tool-name match and text-prefix trigger | Both can trigger | Trigger behavior is not only exact event-name equality |
| Unmatched action with dict or `None` input | `AttributeError` in `Rule.triggered` | A common adapter must explicitly reconcile action-input types |
| Literal and negated predicates | `true`/`false` and single negation behave as recorded; `!!true` is false and `!!false` is true | Do not assume standard repeated-negation semantics; diagnose/repair transparently before fair comparisons |
| Parsed custom predicate function | Current inspected interpreter branch raises `ValueError` | Grammar acceptance does not establish runtime implementation |
| Parsed `invoke_action(...)` | Full parsed dispatch key is absent from inspected enforcement mapping | Do not claim this particular LangChain route executes a replacement just because grammar/README mentions it; other translator paths were not tested |

No defect is used to weaken the comparison baseline or improve CoProCon's scores.
These findings require explicit version/adapter decisions, not a claim that the
whole AgentSpec system is ineffective. Its working manually authored predicates
and supported enforcement paths remain essential strong controls.

## Evidence, accounting and decision

Runner: `research/scripts/probe_agentspec_parser.py`.
Fixture: `research/fixtures/agentspec_parser_fixture.py`.
Evidence root: `artifacts/research/agentspec_audit_20260916`.

Final protocol:
`633867c75a6a51802a7fb4bbfc0652f893af04db94b8d1573da7d4dcbc00cce6`.
Final two-repeat audit:
`585fcec007fc805c2d4667fa073d6b79c29b7badf28ad55e3dfc033aaa7a4c7c`.
An earlier two-repeat result before lint-only comment cleanup remains intact:
`82cc9e2d43b12b4fcb6b6245dd7f79072c3847d2d2c080a07058e8e742409863`.
The observed result payload is identical across both fixture revisions. A host
display pipeline stopped early after the final audit was already stored; rerunning
with complete stdout returned exit code zero and reused the saved native runs.
No native fixture failure or result was discarded. Lint now passes for these files.

Total: four fixture container executions over the two versions, zero model calls,
zero real enforcement actions, zero benchmark episodes, zero API USD. The small
dependency wheel was downloaded without altering the host Python environment.

**KEEP the native parser/Rule and source-body fixtures as adaptation evidence.**
Full framework installation, predicate semantics on shared public artifacts,
budgeted supported recovery, learned-versus-manual rule generation and an identical
benchmark adapter remain open. This is not an end-to-end or published-score
reproduction, and no new novelty or superiority claim follows from it.
