"""Direct DeepSeek boundary; dispatch is forbidden unless explicitly enabled."""
from __future__ import annotations
from typing import Any, Callable, Mapping
from .appworld_live_smoke import ModelOutcome
class DirectDeepSeekSmokeTransport:
    endpoint="https://api.deepseek.com/chat/completions"; model="deepseek-flash"
    def __init__(self, dispatch: Callable[[Mapping[str,Any]], Mapping[str,Any]]|None=None): self.dispatch=dispatch
    def call(self, *, prompt:str, tools:Mapping[str,Any], max_tokens:int)->ModelOutcome:
        if self.dispatch is None: raise RuntimeError("paid dispatch disabled")
        body={"model":self.model,"messages":[{"role":"user","content":prompt}],"tools":tools,"max_tokens":max_tokens,"stream":False,"reasoning_effort":"none"}
        raw=self.dispatch(body); usage=raw.get("usage",{}); message=(raw.get("choices") or [{}])[0].get("message") or {}
        return ModelOutcome(message,int(usage.get("prompt_tokens",0)),int(usage.get("completion_tokens",0)),float(usage.get("cost",0.0)),float(raw.get("latency_seconds",0.0)),(raw.get("choices") or [{}])[0].get("finish_reason",""),raw.get("model",""),len(message.get("tool_calls") or [])==1 and not message.get("reasoning_content"))
