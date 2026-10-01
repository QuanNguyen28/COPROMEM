# Engineering 001 checkpoint-settlement interval forensic

## Disposition

`reasoningbank_appworld_engineering_001` is preserved as
**INFRASTRUCTURE-FAILED — checkpoint settlement interval bug**.  Its four
scored artifacts and all original evidence remain immutable and are not input
to Engineering 002 analysis.

## Read-only finding

The first Dynamic completion marker is a legacy marker: it records the three
update settlements (judge, extraction, document embedding) but has no end of
ledger interval.  Its intent begins at byte `29109`; the named settlement rows
end at byte `30504`.  The run ledger subsequently contains the second
trajectory's executor and query-retrieval rows through byte `38043`.  The old
reconciler used ledger EOF when the next update intent was absent, so it
incorrectly compared the first marker's three IDs with later unrelated IDs.

This is a checkpoint-boundary defect.  It is not a provider, scorer, task, or
ReasoningBank-method failure.  The second Dynamic trajectory is scored but has
no post-score update intent, snapshot, verifier dump, or completion marker.

## Repair

New markers bind a closed, record-aligned ledger interval with:

- `ledger_settlement_end_byte_offset`;
- `ledger_settlement_interval_sha256`; and
- the ordered lifecycle settlement IDs.

Reconciliation validates exactly that interval: one reservation and one
settlement each for judge → extractor → document embedding, with matching
roles and no unbound lifecycle settlement.  Later executor or retrieval calls
are outside the interval.  For legacy markers only, the end is derived from
the final byte of the uniquely named settlement records; the same strict
interval validation is then applied.

The repair never treats a whole-ledger subset as sufficient and never replays
an ambiguous update.
