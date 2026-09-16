# Official train archive found: metadata result and selective public-file gate

Recorded 2026-09-16 after cycle 15 completed. This advances source feasibility,
not contract learning or a benchmark comparison. Branch and project HEAD remain
unchanged; no commits, pushes, original-document or vendor changes.

## Metadata result

The [0.1.3 inventory gate](032_ARCHIVE_V010_RESULT_AND_V013_INVENTORY_GATE.md)
succeeds. Archive SHA256:
`e5ec6367d32b1883d28aaa25e4fe5026c89a08d5fb7a5742a83bfb65fe6bb2da`,
179,524,924 bytes; decrypted ZIP SHA256:
`255a3063f4208636280dd527e1364adafa5e81f7732a221463b664046a7c41a9`.
There are 150,212 central-directory entries. **No ZIP member body was opened**.

Unlike archive 0.1.0, paths are nested by agent/model/split. The initial listing
only recognized a top-level train-labelled experiment and therefore found zero
selected entries. The unmodified archive was then listed again with nested path
metadata. This parser correction changes neither selected tasks nor the no-body
access rule. Both inventories and their implementation snapshots are retained;
the first zero count is not evidence that this archive lacks train data.

Exactly one train-labelled run covers our fixed eight build tasks:
`legacy_react_code_agent/openai/gpt-4o-2024-05-13/train`.
Each task has 18 filenames: 12 simulator DB files, two public logs, two source/data
version files and two evaluator files. Only **filenames, byte sizes and ZIP CRCs**
have been inspected, including for those forbidden DB/evaluator files. No content,
outcome, demonstration, source program or evaluator assertion has been viewed.

Store: `artifacts/research/official_appworld_train_source_20260916_v013`.

- Initial top-level inventory: `be224b89a79cd065b97aac598beb6d99814a8fc5efb45958848973d82adcb940`.
- Correct nested inventory: `9a43b08f57874a1e209cbbb40d87c4b145a9179c42f2a3e3993256aae79a1414`.
- Nested listing source binding: `b164359bb2ac18a7385e23a440dfb4c89d13cc779da85fed21ffa6c05702ac1c`.

**KEEP** this route for selective source inspection under the following gate.
Availability is not competence, absence of leakage, compatible native state,
reproduction or a successful donor. The older test-only archive remains excluded.

## Next gate, frozen before opening selected payloads

Use only the exact train run above and these eight tasks, in the original order:
`27e1026_1`, `b7a9ee9_1`, `60d0b5b_1`, `aa8502b_1`, `ce359b5_1`, `cf6abd2_1`,
`287e338_1`, `3c13f5a_1`. No alternate task, model/run, seed or successful-only
selection is allowed. Decode **exactly four allowlisted files per task**:

- `logs/environment_io.md`;
- `logs/api_calls.jsonl`;
- `version/code.txt`;
- `version/data.txt`.

Require an exact inventory/size/CRC match to the pinned metadata, safe member
paths, no duplicate names or symlinks, at most 1 MB per selected file and 4 MB
total. Extract only these 32 members, in an isolated process with no network or
credentials, to a new write-once selected-public store. Hash each extracted byte
sequence. Never use `extractall`, read any `dbs/` or `evaluation/` member body,
or open another split/task's payload. Keep the archive immutable.

The first question is whether these public logs can be parsed faithfully and
their recorded environment versions identified. Inspect the official public
serialization/parser implementation before writing the parser. Parse all eight
tasks; preserve raw logs and reject ambiguous/truncated/malformed structures.
Do not repair generated Python, infer missing steps, substitute API logs for
missing code or strip inconvenient errors. Program text is untrusted data and
must not be executed in the host process.

This gate permits **extraction and source-format/provenance analysis only**:
zero model calls, zero native task executions, no success labels, no donor
admission. Report all task inventories, program counts, versions, parse failures,
public API/code restrictions and available source-policy/demonstration provenance.
Do not print simulated tokens or bulk raw logs into the user-facing transcript.

**KEEP** the extracted corpus for a separately frozen replay gate only if all
32 requested members are integrity-bound and the parser handles each task without
manual edits. If it fails, **REVISE** the format/provenance assumption, retaining
all failures; no fallback to hidden evaluator/DB files is permitted. Even a
successful extraction leaves source policy, demonstration leakage and matching
of original versus local native versions to be examined before donor use.

The next replay experiment must run every chosen source program unchanged under
the shared isolated policy, preserve unsupported-state/action errors and compare
fresh independent prefixes with native scoring. Published labels, or the archive
directory's model name alone, cannot prove replay eligibility. No such replay has
yet been implemented or run in this record.

Any later policy/memory comparison must share this offline source corpus and
disclose different source-agent/model/demonstration settings and unavailable
historical acquisition costs. A zero new API bill is not zero lifecycle cost.
Cross-task scope, static/text/equal-compute controls and held-out transfer remain
unmet regardless of archive feasibility.
