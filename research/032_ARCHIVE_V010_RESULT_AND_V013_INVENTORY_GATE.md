# Archive 0.1.0 result and 0.1.3 metadata-only follow-up

Recorded 2026-09-16. The [first metadata gate](031_OFFICIAL_TRAIN_ARCHIVE_INVENTORY_GATE.md)
completed with zero model calls, zero task executions and zero ZIP member bodies
opened. All 139,370 entries belong to 28 test-labelled experiment directories.
There is no train-labelled experiment or selected-build entry. **REVISE** the
assumption that the older release used by our installed package contains the
training runs mentioned in the current README. Never use these test trajectories
for induction or source-policy tuning.

Archive: 83,466,311 bytes, SHA256
`1a80df83d1061133da8952714cf0d20c7867d49201e7fea50909f323d77609af`.
Metadata inventory:
`artifacts/research/official_appworld_train_source_20260916/inventories/49c9c67ddc484c2b4c525a168cb4274352343c182ec28b14fef65e2932eb9659.json`.
The original encrypted archive and inventory implementation snapshot remain.

## Next metadata gate, frozen before downloading the newer archive

The [current official constants](https://github.com/StonyBrookNLP/appworld/blob/main/src/appworld/common/constants.py)
declare `EXPERIMENT_OUTPUTS_VERSION = '0.1.3'` and `DATA_VERSION = '0.2.0'`.
Only these version constants and public download source were inspected; do not
equate archive version with native task-data compatibility. HEAD for the official
`experiment-outputs-0.1.3.bundle` reports 179,524,924 bytes, last modified
2025-10-16. This explains a plausible release mismatch, not yet usable train data.

Repeat only the central-directory listing operation on that exact public URL,
with a 200 MB cap and a **new** artifact directory
`artifacts/research/official_appworld_train_source_20260916_v013`.
Use exclusive creation, content integrity checks and the same native bundle
decryption implementation. Allow 2 GiB for the isolated metadata process because
it retains ciphertext and decrypted ZIP buffers; this does not alter any agent
execution worker, source policy or evaluator. No new paid API budget is used.

The task set, no-member-body-access rule and KEEP/REVISE gate are unchanged.
No payload from train, dev or test may be decompressed in this stage. A train
directory covering the fixed eight build IDs merely permits a separately frozen
source-provenance/parser/replay protocol. If decryption/version compatibility
fails, retain the failure and inspect public format code only. No fallback to
test data or relabelling of reserved tasks is permitted.

Command: `python research/scripts/fetch_appworld_output_inventory.py --version 0.1.3`.
The old default remains 0.1.0 and its existing archive is never overwritten.
