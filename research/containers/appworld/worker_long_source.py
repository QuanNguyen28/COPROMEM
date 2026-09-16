"""Versioned offline-source capacity; original action language remains unchanged."""

import copromem_worker_base as base

MAX_ACTIONS = 100
base.MAX_ACTIONS = MAX_ACTIONS

if __name__ == "__main__":
    base.main()
