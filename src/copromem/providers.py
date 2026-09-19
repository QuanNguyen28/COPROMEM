"""Budget-reserving OpenRouter transport for small recorded research pilots."""

from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.request
from typing import Any

from .checkpoints import RunStore
from .real_gsm8k_experiment import OPENROUTER_URL, CallResult, Usage


class BudgetExceeded(RuntimeError):
    pass


class BudgetLedger:
    """Reserve an upper bound before every HTTP attempt, including retries.

    Failed/ambiguous attempts retain their full reserve. Settled usage refunds the
    difference. The ledger is append-only and survives process interruption.
    """

    def __init__(self, store: RunStore, max_usd: float, max_attempts: int):
        if not 0 < max_usd <= 5 or max_attempts < 1:
            raise ValueError(
                "pilot cap must be in (0, 5] USD with positive attempt cap"
            )
        self.store = store
        self.max_usd = max_usd
        self.max_attempts = max_attempts
        self.reservations: dict[str, float] = {}
        self.settlements: dict[str, float] = {}
        store.write(
            "budget", "policy", {"max_usd": max_usd, "max_attempts": max_attempts}
        )
        if store.root:
            for path in (store.root / "reservations").glob("*.json"):
                self.reservations[path.stem] = json.loads(
                    path.read_text(encoding="utf-8")
                )["reserved_usd"]
            for path in (store.root / "settlements").glob("*.json"):
                self.settlements[path.stem] = json.loads(
                    path.read_text(encoding="utf-8")
                )["actual_usd"]

    @property
    def charged_or_reserved(self) -> float:
        return sum(
            self.settlements.get(key, value) for key, value in self.reservations.items()
        )

    def reserve(self, bound: float) -> str:
        if any(
            self.settlements.get(key, 0) > value + 1e-9
            for key, value in self.reservations.items()
        ):
            raise BudgetExceeded(
                "prior provider reservation overrun; no further requests allowed"
            )
        if (
            not math.isfinite(bound)
            or bound < 0
            or self.charged_or_reserved + bound > self.max_usd
        ):
            raise BudgetExceeded("pilot USD reservation cap reached")
        if len(self.reservations) >= self.max_attempts:
            raise BudgetExceeded("pilot HTTP attempt cap reached")
        key = str(time.time_ns())
        self.store.write("reservations", key, {"reserved_usd": bound})
        self.reservations[key] = bound
        return key

    def settle(self, key: str, actual: float) -> None:
        if not math.isfinite(actual) or actual < 0:
            raise ValueError("invalid provider cost; original reservation retained")
        overrun = actual > self.reservations[key] + 1e-9
        # Even an unexpected overrun is a real charge: record it before stopping.
        self.store.write("settlements", key, {"actual_usd": actual})
        self.settlements[key] = actual
        if overrun:
            raise BudgetExceeded(
                "provider cost exceeded reserved bound; inspect billing before further calls"
            )


class BudgetedOpenRouterClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        provider: str,
        ledger: BudgetLedger,
        *,
        prompt_price_per_million: float = 0.25,
        completion_price_per_million: float = 0.5,
    ):
        for value in (prompt_price_per_million, completion_price_per_million):
            if (
                type(value) not in (int, float)
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError("finite positive token-price ceilings required")
        self.api_key = api_key
        self.model = model
        self.provider = provider
        self.ledger = ledger
        self.prompt_price = prompt_price_per_million
        self.completion_price = completion_price_per_million
        self.seed = None
        self.calls = 0
        self.http_attempts = 0
        self.failed_http_attempts = 0
        self.spent_usd = 0.0

    @property
    def request_configuration(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "allow_fallbacks": False,
            "max_prompt_price_per_million": self.prompt_price,
            "max_completion_price_per_million": self.completion_price,
        }

    def chat(
        self, system: str, user: str, max_tokens: int, *, seed: int | None = None
    ) -> CallResult:
        if max_tokens < 1 or self.prompt_price <= 0 or self.completion_price <= 0:
            raise ValueError("positive token/price caps required")
        provider_block: dict[str, Any] = {
            "allow_fallbacks": False,
            "require_parameters": True,
            "max_price": {
                "prompt": self.prompt_price,
                "completion": self.completion_price,
            },
        }
        if self.provider:
            provider_block["only"] = [self.provider]
        body = {
            "model": self.model,
            "temperature": 0,
            "seed": seed,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "provider": provider_block,
        }
        # One token per UTF-8 byte plus generous chat framing overhead bounds
        # this text-only request; server-side endpoint price caps also apply.
        bound = (
            (len(system.encode("utf-8")) + len(user.encode("utf-8")) + 1024)
            * self.prompt_price
            + max_tokens * self.completion_price
        ) / 1_000_000
        started = time.perf_counter()
        for attempt in range(3):
            reservation = self.ledger.reserve(bound)
            request = urllib.request.Request(
                OPENROUTER_URL,
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "X-Title": "CoProCon paired research pilot",
                },
                method="POST",
            )
            self.http_attempts += 1
            try:
                with urllib.request.urlopen(request, timeout=45) as response:
                    result = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                self.failed_http_attempts += 1
                self.ledger.store.write(
                    "transport_attempts",
                    reservation,
                    {
                        "status": "http_error",
                        "http_status": exc.code,
                        "model": self.model,
                        "provider": self.provider,
                    },
                )
                if exc.code not in {429, 502, 503, 504} or attempt == 2:
                    err_msg = ""
                    try:
                        err_data = json.loads(exc.read().decode("utf-8", errors="replace"))
                        err_msg = err_data.get("error", {}).get("message", "")
                    except Exception:
                        pass
                    msg = f"OpenRouter HTTP {exc.code}" + (f": {err_msg}" if err_msg else "")
                    raise RuntimeError(msg) from None
                time.sleep(0.5 * (attempt + 1))
            except (OSError, ValueError):
                self.failed_http_attempts += 1
                self.ledger.store.write(
                    "transport_attempts",
                    reservation,
                    {
                        "status": "transport_or_json_error",
                        "model": self.model,
                        "provider": self.provider,
                    },
                )
                if attempt == 2:
                    raise RuntimeError(
                        "OpenRouter transport or JSON failure; reservation retained"
                    ) from None
                time.sleep(1.0 * (attempt + 1))
        raw = result.get("usage") or {}
        actual = float(raw["cost"]) if raw.get("cost") is not None else bound
        self.ledger.settle(reservation, actual)
        self.spent_usd += actual
        self.calls += 1
        choice = (result.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content")
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        usage = Usage(
            prompt_tokens=int(raw.get("prompt_tokens") or 0),
            completion_tokens=int(raw.get("completion_tokens") or 0),
            total_tokens=int(raw.get("total_tokens") or 0),
            cached_tokens=int(
                (raw.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
            ),
            reasoning_tokens=int(
                (raw.get("completion_tokens_details") or {}).get("reasoning_tokens")
                or 0
            ),
            usd=actual,
            latency_seconds=time.perf_counter() - started,
        )
        return CallResult(
            content if isinstance(content, str) else "",
            usage,
            str(result.get("model", self.model)),
            {
                "provider_response_id": result.get("id"),
                "provider": result.get("provider"),
                "system_fingerprint": result.get("system_fingerprint"),
                "request_seed": seed,
                "finish_reason": choice.get("finish_reason"),
                "raw_usage": raw,
                "cost_is_reserved_upper_bound": raw.get("cost") is None,
                "budget_reservation": reservation,
            },
        )


def model_endpoints(model: str) -> dict[str, Any]:
    url = "https://openrouter.ai/api/v1/models/" + model + "/endpoints"
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))["data"]
