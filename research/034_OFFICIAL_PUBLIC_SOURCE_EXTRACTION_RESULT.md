# Official training logs: extraction and source-provenance result

2026-09-16; previous goal turn **progress** (complete cycle-15 null result,
baseline fixtures and metadata gates). Branch `codex/copromem-research-loop`,
unchanged HEAD `18025102c010e85f26b0b3fb1144a1cb684b587e`.

## Result of the frozen 32-file gate

**KEEP** for the next native replay gate, not for donor admission. Exactly 32
allowlisted public log/version members were extracted (255,486 bytes), with zero
database/evaluator/other-task member bodies read. All eight logs parse without
manual edits. A lossless parser preserves exact code/output source spans and
agrees exactly with the installed native parser on all fields in this corpus;
no whitespace normalization was needed. Sixteen authored tests cover grammar,
source spans, malformed/ambiguous logs, path/split selection, duplicate ZIP names,
CRC/size mismatches, symlinks and size caps. No source program has been executed.

| Build task | Archived interactions | API log rows | Recorded code/data version |
|---|---:|---:|---|
| 27e1026_1 | 17 | 20 | 0.1.0 / 0.1.0 |
| b7a9ee9_1 | 11 | 74 | 0.1.0 / 0.1.0 |
| 60d0b5b_1 | 13 | 30 | 0.1.0 / 0.1.0 |
| aa8502b_1 | 12 | 44 | 0.1.0 / 0.1.0 |
| ce359b5_1 | 8 | 28 | 0.1.0 / 0.1.0 |
| cf6abd2_1 | 10 | 10 | 0.1.0 / 0.1.0 |
| 287e338_1 | 8 | 7 | 0.1.0 / 0.1.0 |
| 3c13f5a_1 | 85 | 84 | 0.1.0 / 0.1.0 |

Total 164 interactions. The installed action-language static precheck accepts
all code, but this does not establish runtime-bound namespace safety, compatible
API responses, successful execution, original outcomes or replay equivalence.
The current native dataset's `version.txt` is also 0.1.0; the installed package is
0.1.3.post1. Matching dataset version labels alone do not prove byte-identical
original task states or complete historical reproducibility.

The 85-interaction record exceeds the existing 50-action worker capacity. It is
preserved, not truncated or silently executed under a larger budget. A separately
registered bounded runtime gate is required before replaying all eight records.

## Source-policy audit and limitations

The [pinned current legacy train configuration](https://github.com/StonyBrookNLP/appworld/blob/42b5bcf3cd334fee33f0c37c02070a9f5807add5/experiments/configs/legacy_react_code_agent/openai/gpt-4o-2024-05-13/train.jsonnet)
uses a single ReAct policy, a named dated GPT-4o model, temperature zero, seed 123,
400 output tokens, a 50,000-character prompt cap and a 100-LLM-call stop. This is
not our fixed two-role Qwen collector, its prompts, seeds or budget. The metadata
does not bind every historical request to this later repository revision.

The generic legacy prompt contains a worked Spotify playlist-counting example,
not just API specifications. That is human-authored guidance and a potential
strong static/textual competing explanation; it is not learned CoProCon logic.
The current legacy prompt is byte-identical to the `react.txt` prompt in the
official v0.1.0 source tree (`0a749f16da0c516811fe58e59ec9e2217560f54d`). It has no
literal benchmark task IDs. This supports prompt provenance but does not certify
absence of every possible example overlap or prove the exact original run prompt.
No reserved task specifications were opened to force such a comparison.

Both historical and current prompted-loader code prepare a `relevant_apis` field
from task ground truth. The inspected prompt has no such placeholder or literal
reference; it uses public user/app/input fields. Preparation is therefore **not
evidence that required-API labels actually entered this ReAct prompt**. Conversely,
this narrow static check is not an exhaustive leakage proof. The inspected reader
emits a placeholder gold answer, and the environment answerer evaluates after
the generated trajectory; no hidden evaluator reports were extracted from the
archive or supplied to our source parser.

Public general source/config/template files are stored with URLs, revisions and
hashes under `source_policy_files`. They are distinct from forbidden archive
task payloads. No cloud key or paid model was used. Unknown original acquisition
costs remain unknown, not zero. Any later learned/control comparison must share
the offline corpus and disclose its policy/demo differences and provenance limits.

## Reproduction addresses and next gate

Store: `artifacts/research/official_appworld_train_source_20260916_v013`.
Extraction protocol/report key:
`bfc1c31b1818cfa088308ae2bd041b4546177db6a202c91517671fd19ae56bc8`.
Container run:
`b8908bd51d5c9ece370de0c58e619197cb32d3aafd57580c9e6b8764735bd1a9`.
Raw files and parsed records live in `selected_public/<protocol-key>/` with
per-file hashes and exact member allowlist. Implementation, native parser/writer
source, image and preregistration are archived. The original encrypted release
and initial inventory mistakes remain intact. No native outcome is known yet.

Next: a separate 100-action source-replay runtime gate, preserving the 50-action
image and existing source protocols, followed only on success by a frozen all-eight
local replay diagnostic. This expands infrastructure explicitly; it does not
authorize extra paid retries or change historical outcomes/eligibility. Full
source-policy reproduction, learned scope, static/equal-compute comparisons and
held-out advantage remain unestablished.
