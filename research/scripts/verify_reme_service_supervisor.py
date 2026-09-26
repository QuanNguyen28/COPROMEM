#!/usr/bin/env python3
"""Deterministic zero-model regression for concurrent ReMe service supervision."""
from __future__ import annotations

import importlib.util, pathlib, sys, types

ROOT = pathlib.Path("/mnt/e/Project/AAMAS/COPROMEM")
spec = importlib.util.spec_from_file_location("reduced_v2_runner", ROOT / "scripts/run_official_reme_copromem_reduced_v2.py")
module = importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(module)


class FakeProcess:
    returncode = None
    def poll(self): return self.returncode
    def terminate(self): self.returncode = 0
    def wait(self, _=None): return 0
    def kill(self): self.returncode = -9


def main() -> None:
    started: list[FakeProcess] = []
    original_popen, original_urlopen = module.subprocess.Popen, module.urllib.request.urlopen
    module.subprocess.Popen = lambda *a, **k: (started.append(FakeProcess()) or started[-1])
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
    module.urllib.request.urlopen = lambda *a, **k: Response()
    try:
        with module.reme_services("deterministic-restart-test") as urls:
            assert urls == ("http://127.0.0.1:18102/", "http://127.0.0.1:18103/")
            assert len(started) == 2
        assert all(p.returncode == 0 for p in started)
    finally:
        module.subprocess.Popen, module.urllib.request.urlopen = original_popen, original_urlopen
    print("reme_service_concurrent_startup_restart_regression=passed")


if __name__ == "__main__": main()
