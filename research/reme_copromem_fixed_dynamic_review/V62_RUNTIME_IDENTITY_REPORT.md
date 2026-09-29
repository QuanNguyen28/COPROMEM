# v6.2 runtime-content identity report

This report records a zero-provider preflight only. Local paths are resolved
through the ignored `/.copromem-runtime.json` configuration and are not part
of the semantic identity. The tracked example contains placeholders only.

## Logical runtime mapping

| Logical component | Local configuration key | Semantic binding |
| --- | --- | --- |
| Upstream ReMe source | `reme_source` | Git commit, dirty-content hash, source-tree hash, agent hash |
| ReMe interpreter | `reme_python` | executable content hash and CPython version |
| AppWorld source/runtime | `appworld_root` | installed package/evaluator/package-tree hashes |
| AppWorld interpreter | `appworld_python` | executable content hash and CPython version |

The preflight was executed from the configured AppWorld interpreter. It found
`appworld==0.1.3.post1`, CPython 3.12.3, and the upstream ReMe commit
`2f37a159b72a04ac1885a7db7f1a663a833e7791` with a clean tree. The pinned
ReMe environment reports AgentScope 1.0.20 and FlowLLM 0.2.0.10.

The runtime identity schema is `runtime-content-identity-v2`. Its components
are: evaluation runner, task query, semantic lifecycle, evidence contract,
CoProMem and ReMe checkpoints, terminal reconciler, bridge, AppWorld worker,
callable registry, protocol decisions, dependency lock, both interpreter
executables, upstream ReMe agent/tree, installed AppWorld package/tree, and
official AppWorld evaluator. Each is content-addressed; no absolute path,
credential, task payload, database, cache, journal, or scorer output is
represented.

The WSL view of the linked CoProMem worktree is dirty. This is not ignored:
the record includes `copromem_git_dirty=true` and a deterministic dirty-content
hash. A changed tracked or non-ignored untracked source file changes that
identity and blocks a frozen manifest at verification.

## Portability dispositions

1. The Windows-versus-WSL E-drive fixture assertion is fixture-only. The
   production preflight runs under the configured WSL interpreter and the
   runtime record is path-independent.
2. The subprocess import-path fixture is fixture-only. The maintained service
   boundary explicitly exports `PYTHONPATH` for its bridge package.
3. The linked-worktree Git-pointer fixture is portability-only for Windows.
   The production WSL source resolver translates the linked Git directory and
   was exercised by this preflight.

No provider, service, AppWorld task, scorer, lifecycle, embedding, payload,
or runner was invoked.
