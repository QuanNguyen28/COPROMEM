# Cycle 23 input preflight: complete, generation not started

Recorded 2026-09-16 on `codex/copromem-research-loop`, HEAD
`18025102c010e85f26b0b3fb1144a1cb684b587e`. This reports an implementation stage
of [protocol 053](053_CYCLE23_MONITOR_PROPOSAL_PROTOCOL.md), not the cycle's
primary candidate-construction result. No candidate has been generated or scored.

The new `monitor_proposal_inputs.py` reconstructs the full cycle-22 independent
audit and selects only the two registered failure/repair pairs at matching
contexts. It prepares all 12 fold/mode/seed requests and all 14 diagnostic
runtime records. Success-only requests omit failed examples; neither mode
contains the other fold's examples, source identifiers or hidden state.

Runtime inputs contain only normalized program text and sorted public present
names. String literals are replaced uniformly; comments disappear through AST
normalization. The actual source programs remain untouched. Normalized code is
not executed, and saved native labels describe original source executions, not
fresh execution of the normalized text. This representation loses string-content
semantics and is therefore explicitly limited. Labels/provenance are separate
from the generated check's runtime input.

All 14 runtime records happen to have distinct normalized-input digests; this
does not make them independent tasks. There are still only two known build
scenarios and three previously inspected contexts.

## Evidence and repeat

Root: `artifacts/research/cycle23_monitor_inputs`.

- Complete input report: `2890a5e8a9eebbd78e0f737bb2214f3a66585847946bc7b0a6c6963fb2f0f48f`.
- Constructor/protocol/test snapshot: `7946e70992bf7601847cca19264126cdd8ddcc0d649485526d6205604c22e90e`.
- Reconstructed cycle-22 audit: `29a92ada86516322f635750c6d685e2dc6d6190cc59834f5f5471b071cf16fa5`.

Two serial preflight invocations yield the same report and complete write-once
inventories. Eleven new focused fixtures cover input immutability, literal
redaction, no code execution, unknown coverage, forbidden fields, exact paired
contexts/outcomes, success-only evidence isolation, fold withholding and byte-
literal quarantine. The complete suite passes **415 tests**. New files are
lint-clean; the earlier frozen runner's FURB192 style warning remains disclosed.

```powershell
$env:PYTHONPATH='src'
python research/scripts/monitor_proposal_inputs.py
python -m pytest -o addopts= -q
```

Model requests actually sent: **0**. Native executions/scorers: **0**.
New API USD: **0**. Generated or admitted contracts: **0**. Twelve is a prepared
request count, not a completed-call count. Prior paid accounting is unchanged.

## Pending stage and constraints

Next implement and test the restricted generated-source parser and isolated,
resource-limited runtime with no host mounts, secrets or network. Validate its
failure/timeout/label-isolation paths on constructed fixtures, then freeze its
source/image/prompt/configuration alongside these inputs. Verify current provider
endpoint metadata before any paid generation. Preserve partial attempts and do
not silently replace candidates, models or source pairs.

Only after those checks can the 12-request proposal diagnostic run under the
registered USD 5 cap. All outputs, abstentions and failed candidates must remain
in its denominator. Primary KEEP/REVISE is **pending**, not inferred from this
engineering preflight. A later method comparison still needs a competent manual
semantic control, anti-shortcut tests, matched recovery, scope and untouched-
group evaluation. The research objective remains active and unresolved.

### Dated selected-scope credential check

Exact configured-key byte audit
`5eb7e958b91c33838bef0f806324cd20f1ab4b6aec46b8ab4b53dda73168b8ef`
scans 2,110 files / 14,826,490 bytes with zero matches and zero unreadable files.
The saved record lists source/tests/research/docs and cycle-18 through cycle-23
stores included in this check. It excludes `.env`, Git internals and unlisted
old evidence; it is non-atomic and does not detect arbitrary encoded or unrelated
secrets. Earlier wider-scope audits remain separately preserved. No key value
is printed or persisted by this audit.
