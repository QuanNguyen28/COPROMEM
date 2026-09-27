"""Fail closed on nonlocal Python network calls in the Ollama pilot process."""

from __future__ import annotations

import os
import socket
import sys
import importlib.util
from pathlib import Path


if os.environ.get("COPROMEM_LOCAL_ONLY") == "1":
    _connect = socket.socket.connect
    _connect_ex = socket.socket.connect_ex

    def _check(address: object) -> None:
        if isinstance(address, tuple):
            host = str(address[0]).lower().strip("[]")
            if host not in {"localhost", "127.0.0.1", "::1"}:
                raise OSError(f"COPROMEM local pilot blocked nonlocal connection: {host}")

    def _local_connect(self: socket.socket, address: object) -> None:
        _check(address)
        return _connect(self, address)

    def _local_connect_ex(self: socket.socket, address: object) -> int:
        _check(address)
        return _connect_ex(self, address)

    socket.socket.connect = _local_connect
    socket.socket.connect_ex = _local_connect_ex

    adapter_path = os.environ.get("COPROMEM_PILOT_ADAPTER")
    if adapter_path:
        spec = importlib.util.spec_from_file_location("copromem_adapter", Path(adapter_path))
        if spec is None or spec.loader is None:
            raise RuntimeError("Cannot load tracked COPROMEM adapter")
        module = importlib.util.module_from_spec(spec)
        sys.modules["copromem_adapter"] = module
        spec.loader.exec_module(module)
