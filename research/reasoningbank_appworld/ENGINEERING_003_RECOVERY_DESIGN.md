# Engineering 003 recovery design

Engineering 003 is a bounded infrastructure recovery, not a new allocation.
It uses the Engineering 002 A/B/N order and imports exactly one immutable
completed No Memory artifact through a custody envelope.  The envelope binds
the predecessor manifest, artifact, history, execution journal, scorer
evidence, and settled executor IDs by hash.  It never copies the artifact,
journal, scorer output, or prior ledger rows.

The new ledger has one manifest-pinned historical carry record for all prior
exposure.  It is reconciled separately from successor arm costs.  Completion
counts the imported key only after an fsynced, reload-verified import marker;
the runner skips that exact key and continues from the next ordered key.
