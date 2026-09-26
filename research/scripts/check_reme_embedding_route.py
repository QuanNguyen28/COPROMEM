#!/usr/bin/env python3
"""Sanitized, zero-cost configuration gate for official ReMe embeddings."""
from __future__ import annotations

import pathlib
import subprocess
import urllib.parse

ROOT = pathlib.Path("/mnt/e/Project/AAMAS/COPROMEM")
ENV_FILE = ROOT / ".env"
OFFICIAL_BASES = {
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    "https://dashscope-sg.aliyuncs.com/compatible-mode/v1",
}
REQUIRED = ("FLOW_EMBEDDING_API_KEY", "FLOW_EMBEDDING_BASE_URL")


def env_values() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_FILE.exists():
        return values
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() in REQUIRED:
            values[name.strip()] = value.strip().strip("'\"")
    return values


def main() -> None:
    values = env_values()
    ignored = subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=ROOT).returncode == 0
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", ".env"], cwd=ROOT,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    print("provider=Alibaba_Cloud_Model_Studio_DashScope")
    print("model=text-embedding-v4")
    print("endpoint_family=DashScope_OpenAI_compatible_/embeddings")
    print("request_shape=OpenAI_embeddings.create(model,input,dimensions=1024,encoding_format=float)")
    print("credential_variable=FLOW_EMBEDDING_API_KEY")
    print("base_url_variable=FLOW_EMBEDDING_BASE_URL")
    print("dimensions=1024")
    print("env_file_ignored=" + str(ignored).lower())
    print("env_file_tracked=" + str(tracked).lower())
    print("credential_present=" + str(bool(values.get("FLOW_EMBEDDING_API_KEY"))).lower())
    print("base_url_present=" + str(bool(values.get("FLOW_EMBEDDING_BASE_URL"))).lower())
    configured_base = values.get("FLOW_EMBEDDING_BASE_URL", "").rstrip("/")
    parsed = urllib.parse.urlparse(configured_base)
    workspace_singapore = bool(parsed.hostname and parsed.hostname.endswith(".ap-southeast-1.maas.aliyuncs.com"))
    approved_base = configured_base in OFFICIAL_BASES or workspace_singapore
    print("base_url_host=" + (parsed.hostname or "absent"))
    print("base_url_official_dashscope=" + str(approved_base).lower())
    print("ready=" + str(ignored and not tracked and bool(values.get("FLOW_EMBEDDING_API_KEY"))
                         and approved_base).lower())


if __name__ == "__main__":
    main()
