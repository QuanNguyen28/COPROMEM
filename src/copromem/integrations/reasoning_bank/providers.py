"""Pinned, ledgered provider adapters for the ReasoningBank AppWorld port.

The module contains no retry or HTTP implementation.  It delegates every
request to the maintained DeepSeek-only OpenRouter transport, while retaining
only hashes of judge/extractor responses in durable lifecycle records.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ..reme.transport import AppendOnlyLedger, LockedOpenAI
from .appworld import sha256


MODEL = "deepseek/deepseek-v4.1-flash"
JUDGE_ROLE = "reasoningbank_judge"
EXTRACTION_ROLE = "reasoningbank_extraction"
JUDGE_SYSTEM = "You are a helpful assistant that judges whether the agent successfully completed the task."


def _trajectory_text(value: Any) -> str:
    """Canonical public trajectory serialization used at the provider boundary."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class ReasoningBankProviders:
    """Self-judge and extractor callbacks accepted by ``ReasoningBankLifecycle``."""

    def __init__(self, *, api_key: str, ledger: AppendOnlyLedger, progress: Path) -> None:
        self._judge = LockedOpenAI(api_key=api_key, ledger=ledger, progress=progress, role=JUDGE_ROLE)
        self._extractor = LockedOpenAI(api_key=api_key, ledger=ledger, progress=progress, role=EXTRACTION_ROLE)

    @staticmethod
    def _content(response: Any) -> str:
        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError) as exc:
            raise RuntimeError("locked ReasoningBank provider returned no text content") from exc
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("locked ReasoningBank provider returned empty text content")
        return content

    def judge(self, query: str, trajectory: Any, temperature: float) -> tuple[str, Mapping[str, Any]]:
        if float(temperature) != 0.0:
            raise ValueError("ReasoningBank self-judge temperature is frozen at 0.0")
        prompt = (f"Task: {query}\n\nTrajectory:\n{_trajectory_text(trajectory)}\n\n"
                  "Did the agent successfully complete the task? Answer with 'success' or 'fail' only.")
        response = self._judge.chat.completions.create(
            model=MODEL, messages=[{"role": "system", "content": JUDGE_SYSTEM},
                                    {"role": "user", "content": prompt}],
            temperature=0.0, top_p=1.0, stream=False,
        )
        content = self._content(response)
        # This preserves the upstream judge's categorical convention without
        # consulting the official AppWorld score.
        status = "success" if "success" in content.strip().lower() else "failure"
        record = dict(self._judge.chat.completions.last_record or {})
        record.update({"label": status, "response_sha256": sha256(content),
                       "system_sha256": sha256(JUDGE_SYSTEM), "prompt_sha256": sha256(prompt)})
        return status, record

    def extract(self, system_prompt: str, query: str, trajectory: Any, temperature: float) -> tuple[str, Mapping[str, Any]]:
        if float(temperature) != 1.0:
            raise ValueError("ReasoningBank memory extractor temperature is frozen at 1.0")
        # ``system_prompt`` is supplied verbatim by lifecycle.py from the
        # pinned upstream extraction constants.  Do not rewrite it here.
        prompt = f"**Query:** {query}\n\n**Trajectory:**\n{_trajectory_text(trajectory)}"
        response = self._extractor.chat.completions.create(
            model=MODEL, messages=[{"role": "system", "content": system_prompt},
                                    {"role": "user", "content": prompt}],
            temperature=1.0, top_p=1.0, stream=False,
        )
        content = self._content(response)
        record = dict(self._extractor.chat.completions.last_record or {})
        record.update({"response_sha256": sha256(content), "system_sha256": sha256(system_prompt),
                       "prompt_sha256": sha256(prompt)})
        return content, record
