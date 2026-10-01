# CoProMem v6.2.2 comprehensive repair audit

Status: **ENGINEERING-PREFLIGHT-READY; paid confirmatory pilot not yet authorized by this record.**

Executable source commit: `eecadef358938522f96523e5aced5fc5edcd10fd`.
It was validated from a clean detached worktree. The 69-test focused gate,
compilation, imports, diff check, and a second WSL bank rebuild passed there.

This repair is additive to v6.2.1. Historical runs and their method labels are
unchanged.

## Resolved defects

| Defect | Repair | Fail-closed invariant |
|---|---|---|
| Slot-name or registry-edge dataflow inference | Occurrence-level redacted value-equality witnesses are carried from dispatcher graphs into committed schemas | No witness, no prerequisite edge |
| Cross-app input laundering | Input support is checked against an incoming edge to the exact target occurrence or the current public query | No global produced-slot set |
| Ambiguous terminal occurrence | Schema stores one terminal occurrence or one explicit consecutive terminal repetition group | Ambiguous legacy repetition abstains |
| Implicit typed-constraint reuse / ignored extras | Positional constraints cover every occurrence exactly; explicit reusable constraints are the only exception | Missing, extra, duplicate, or misaligned constraints reject |
| Literal repeated-call prompt inflation | Consecutive identical occurrences render as one parameterized repetition instruction | All occurrence IDs/order remain hash-bound in provenance |
| Semantic validator bypass | The v6.2.2 semantic validation result directly gates transactional commit | Base-v6 success cannot override semantic rejection |
| Scored-artifact rewriting | Retrieval/query/prompt custody is an atomic immutable sidecar | Artifact bytes never change after scoring |
| Restart retrieval acceptance without replay | Restart reproduces retrieval from the exact pre-state and verifies artifact, prompt, runtime, and sidecar bytes | Conflicting or partial sidecar fails closed |
| Weak terminal retrieval reconciliation | Every CoProMem artifact/retrieval/sidecar is revalidated before `run_reconciled` | Completion cannot be reported with missing retrieval custody |
| Runtime identity domain collision | Artifact and zero-action evidence bind semantic identity and runtime-record hash separately | Neither identity can substitute for the other |
| Missing zero-action runtime identity | Every production executor call receives the frozen runtime record and semantic identity | Zero-action evidence fails before acceptance if either is absent |
| Windows/WSL evidence path mismatch | Windows paths remain native on Windows; POSIX maps drives to `/mnt/<drive>` | E-backed policy is checked in the native path domain |

## Zero-provider validation

- Focused retrieval, learning, binding, evidence, orchestration, and AppWorld
  suites: 60 passed in the final focused gate.
- A broader focused gate including the maintained v6.1 orchestration shadow:
  69 passed.
- AppWorld evidence suite passes after the native path repair.
- Compilation and diff checks pass.
- The remaining broad-suite exclusions are environment/evidence fixtures:
  WSL-only E-backed integration root, subprocess `PYTHONPATH`, canonical
  historical E-drive audit evidence, and the pre-existing Windows PID probe.

The immutable v6 acquisition was rebuilt offline with the new contract:

- Source manifest: `422a45f8925b82dd83287bb10642a857fd3753b77570ccadb069f4ed310ad607`
- Source pool: `39878442ef832fa75c526f3c1af3be2c4cc052496ba0311bcfdba5b4623b618b`
- Registry: `09325ae59f351b4b18ae5127a456890c844515b872277ba4c133ffbd9c5c4423`
- Rebuilt state: `5d98798f203150dea4011cc6134ac96469cbd1389141757bf2792e6d02db96ce`
- Committed schemas: 5 across 3 families
- Provider/model/scorer/AppWorld calls during rebuild: 0
- Recovery report: `40aa13c3c60f8078a792332f8a817185ff06b815d30a6e586537b234ee32c842`
- The clean-runtime rebuild reproduced that report hash exactly.

## Remaining gates before a real pilot

1. Commit and publish one executable source identity.
2. Validate a clean detached runtime at that exact commit.
3. Freeze the admitted v6.2.2 bank by file and semantic hashes in a new
   allocation/manifest; never point the runner back to the v6.1 bank.
4. Run a zero-provider production shadow from the detached runtime.
5. Run one small engineering integration and require terminal reconciliation.
6. Only then preregister and launch a confirmatory multi-task pilot.

ReasoningBank Engineering 016 is separately engineering-validated. ReMe's
fixed/dynamic checkpoint, ledger, and retrieval-observer suites remain green,
but neither baseline result substitutes for a clean, newly frozen comparative
pilot under this repaired CoProMem method.
