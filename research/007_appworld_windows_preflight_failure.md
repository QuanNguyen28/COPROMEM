# AppWorld native Windows failure and Linux fallback

Date: 16 September 2026. This is adapter engineering evidence, not model performance.

AppWorld 0.1.3.post1 installed into `.research-envs/appworld-013` with Python 3.12.
CLI help and `pip check` succeeded. Package hash and dependency artifacts are in
`artifacts/research/appworld_install_20260916.json`. The official data bundle was
downloaded into a new isolated root after verifying no existing data would be
overwritten; only a train task was selected by the probe. Test-task content has
not been inspected or used for development.

`native-state-v1` selected the lexicographically first train ID. The first authored
read-only API action failed before completing because the released timeout helper
uses `signal.SIGALRM`, unavailable on Windows. The failure then exposed another
integration problem: the in-process safety guard stayed active on this exception
path, intercepting the research logger's file writes. The traceback is in the tool
execution record; the run's write-once preregistration and native partial output
directory are retained. This is not evidence that all AppWorld versions fail on
Windows; it is the observed behavior of this release/configuration.

We did not set `timeout_seconds=None`, disable syntax/runtime guards, or edit vendor
source. An external supervisor process is needed to preserve logs even when an
embedded environment corrupts process-global state. The installed Ubuntu WSL
environment reports Python 3.12.3 and supports the required Linux signal facility.
The next bounded fallback uses a separate Linux virtual environment, the same
released package, existing train data and a new run ID. Only reviewed probe code
may run; no LLM-generated code or paid agent calls are included.
