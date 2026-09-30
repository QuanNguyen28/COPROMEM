# Runtime content identity v3

`runtime-content-identity-v3` is the portable identity boundary for the
v6.2.1 engineering successor. It separately hashes executable source, semantic
runtime configuration, external dependency identities, and scientific inputs.
The aggregate contains only component hashes plus the declared executable Git
commit. It deliberately excludes checkout paths, timestamps, Git-pointer form,
ports, credentials, PIDs, and artifact-junction paths.

The executable inventory is controlled by
`runtime-content-identity-v3-policy.json`: all executable source/configuration
under the policy roots and the maintained entry points are content-addressed.
Dirty checking compares those exact tracked files to the declared commit and
rejects untracked executable/configuration files under a runtime source root.
Publication-only files and untracked reports are not runtime dirt. The policy
only admits textual runtime formats; their source hashes use LF-normalized
Git-equivalent bytes, so a clean CRLF Windows checkout and a clean LF checkout
remain the same executable source. Artifact and scientific-input hashes retain
their exact raw-content semantics.

V2 records remain readable for historical audit. A manifest requiring v3 never
accepts a v2 record. A future runner must call the shared manifest verifier at
startup, restart, before opening each task, and before terminal completion.
