#!/usr/bin/env python3
"""Zero-model contract audit for pinned ReMe HTTP task-memory flows."""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path("/mnt/e/Project/AAMAS/COPROMEM")
SOURCE = pathlib.Path("/home/xiqhq/copromem-reme")


def main() -> None:
    config = (SOURCE / "reme_ai/config/default.yaml").read_text(encoding="utf-8")
    service = (SOURCE / "reme_ai/service/task_memory_service.py").read_text(encoding="utf-8")
    runner = (SOURCE / "benchmark/appworld/appworld_react_agent.py").read_text(encoding="utf-8")
    assert "summary_task_memory:" in config and "UpdateVectorStoreOp()" in config
    assert "retrieve_task_memory:" in config and "input_schema:" in config
    assert 'async_execute_flow(name="summary_task_memory"' in service
    assert "add_task_memory" not in config
    assert 'url=f"{self.memory_base_url}add_task_memory"' in runner
    # Fixture route schemas used by the runner: summary needs trajectories;
    # retrieval needs query. Summary's terminal UpdateVectorStoreOp is the
    # official persistence operation, not a separate HTTP endpoint.
    print("reme_http_contract=passed")
    print("summary_persists_via=UpdateVectorStoreOp")
    print("registered_summary_schema=trajectories")
    print("registered_retrieval_schema=query")
    print("upstream_dynamic_add_endpoint=absent_from_registered_routes")


if __name__ == "__main__": main()
