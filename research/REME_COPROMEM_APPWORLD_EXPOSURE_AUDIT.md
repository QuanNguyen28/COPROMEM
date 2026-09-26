# AppWorld development-scenario exposure audit

## Status: manifests not frozen; pilot NOT READY

No six-task acquisition or eight-task evaluation manifest is frozen in this
repository. Consequently their SHA-256 values are intentionally absent rather
than fabricated.

## Evidence of prior AppWorld exposure

The current CoProMem repository contains substantial earlier AppWorld work,
including `src/copromem/appworld_preflight.py`, AppWorld research containers,
cycle 06/07/08/09/11/14/15 configuration files, and referenced artifact stores
such as `artifacts/research/appworld_preflight_20260916/data` and
`artifacts/research/cycle11_appworld_source`.  The cycle configurations use
train-derived build/dev/audit/evaluation groups and explicitly track prior
selection digests.  This is enough evidence to reject any un-audited AppWorld
development sample as clean.

The official `appworld==0.1.3.post1` data installation exposes 90 `train` and
57 `dev` IDs; the `development` alias is unsupported. `test_normal` was never
queried or opened. A conservative text/artifact pass across `research/`,
`artifacts/`, and
`E:/Project/AAMAS/copromem_artifacts_backup_20260916/` found every one of those
147 development-eligible IDs. It leaves **zero** clean IDs before compressed
or binary backup content is counted. The complete byte-level backup scan was
therefore stopped rather than consuming more time after this decisive result.

No 14-task clean manifest exists and no ID/payload selection is reported as
clean. The source revision for this failed selection gate is
`6eca54ca14a7935fcdcdc1a9a77319ed113a0679`; the registered ordering would have
been ascending SHA-256 of `20260925 + newline + task_id`.

## Required manifest-generation gate

After the official AppWorld package/data revision is pinned, a zero-cost script
must:

1. Enumerate official train/development task IDs and record package/data hashes,
   never querying `test_normal`.
2. Extract every task/scenario ID from tracked source, `research/`,
   `artifacts/`, ignored local artifacts, and
   `copromem_artifacts_backup_20260916/`.
3. Exclude all prior IDs and any task whose instruction/content was examined
   during development.
4. Deterministically choose six acquisition and eight disjoint evaluation IDs
   from the remaining development-only pool using the registered seed.
5. Write immutable JSON manifests, their SHA-256 digests, the exclusion set
   digest, and the audit result under
   `artifacts/research/reme_copromem_comparison/`.
6. Fail closed if fewer than fourteen clean scenarios remain.

Until that gate succeeds, this study is not eligible for paid pilot approval.

## Required alternatives

1. An exposure-labelled plumbing pilot on previously seen development tasks.
   It can validate the adapter, scorer path, and budget guard only; it cannot
   support efficacy or generalization claims.
2. A newly created benchmark/split under defensible custody, with a new
   immutable task inventory, access log, and manifest generated before any
   task payload is inspected.
