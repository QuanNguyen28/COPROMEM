# v6.2 Evaluation 003 Infrastructure Recovery Amendment

Evaluation 002 stopped after ten durable scored trajectories at the first
CoProMem Dynamic task boundary. Its Dynamic pre-state was the accepted v6.1
semantic-content bank encoded in the legacy v6 container. The runner called
the semantic lifecycle, whose former format guard rejected that valid legacy
representation before planning, validation, or commit.

This amendment is infrastructure-only. It permits a separately versioned
successor to import only source-validated scored artifacts, scorer journals,
execution-evidence journals, retrieval records, settled ledger rows, and the
two completed ReMe Dynamic checkpoint chains. The source Evaluation 002 files
remain immutable.

The successor verifies every imported file by hash, rebinds only copied journal
locations under its own run root, and labels each derived artifact with its
source artifact and source manifest hashes. It then reconstructs the one
unstarted CoProMem Dynamic task boundary offline from the two durable source
artifacts. It may not replay an executor, scorer, embedding, lifecycle, or
ReMe Dynamic update request.

The scientific allocation, arms, task order, seeds, models, provider route,
temperature, action limit, initial bank identities, and budget cap remain
unchanged. This does not reinterpret or replace any completed trajectory.
