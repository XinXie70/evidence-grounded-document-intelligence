"""OpenAI Responses wrapper: pinned config, cost ledger with a hard cap, request log."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from egdi.reasoning_api import estimate_cost_usd

CONFIG_PATH = Path("configs/v2_llm.json")


class BudgetExceeded(RuntimeError):
    """Raised before a request when the run's spending cap has been reached."""


class CostLedger:
    """Running total of estimated spend; ``check`` is called before every request."""

    def __init__(self, max_usd: float):
        if max_usd <= 0:
            raise ValueError("max_usd must be positive")
        self.max_usd = max_usd
        self.spent = 0.0
        self.calls = 0
        self._lock = threading.Lock()

    def check(self) -> None:
        with self._lock:
            if self.spent >= self.max_usd:
                raise BudgetExceeded(f"spent ${self.spent:.4f} of the ${self.max_usd:.2f} cap")

    def add(self, cost: float) -> None:
        with self._lock:
            self.spent += cost
            self.calls += 1


@dataclass
class LlmResult:
    response: Any
    usage: dict[str, Any] | None
    cost_usd: float
    latency_s: float


def load_config(root: Path = Path(".")) -> tuple[dict[str, Any], dict[str, Any]]:
    config = json.loads((root / CONFIG_PATH).read_text(encoding="utf-8"))
    pricing = json.loads((root / "configs" / config["pricing_snapshot_path"]).read_text(encoding="utf-8"))
    return config, pricing


def to_openai_tools(schemas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"type": "function", **schema, "strict": False} for schema in schemas]


def json_schema_format(name: str, schema: dict[str, Any]) -> dict[str, Any]:
    return {"format": {"type": "json_schema", "name": name, "strict": True, "schema": schema}}


class LlmClient:
    """One entry point for every paid request, so cost and logging cannot be bypassed."""

    def __init__(
        self,
        config: dict[str, Any],
        pricing: dict[str, Any],
        ledger: CostLedger,
        *,
        log_path: Path | None = None,
        client: Any = None,
    ):
        self.config, self.pricing, self.ledger, self.log_path = config, pricing, ledger, log_path
        if client is None:
            from openai import OpenAI  # reads OPENAI_API_KEY

            client = OpenAI(max_retries=config["max_retries"], timeout=config["timeout_seconds"])
        self.client = client

    def respond(
        self,
        *,
        label: str,
        input: Any,
        instructions: str,
        tools: list[dict[str, Any]] | None = None,
        text: dict[str, Any] | None = None,
        tool_choice: Any = None,
        include: list[str] | None = None,
        max_output_tokens: int | None = None,
    ) -> LlmResult:
        self.ledger.check()
        request: dict[str, Any] = {
            "model": self.config["model"],
            "instructions": instructions,
            "input": input,
            "reasoning": {"effort": self.config["reasoning_effort"]},
            "max_output_tokens": max_output_tokens or self.config["max_output_tokens"],
            "store": self.config["store"],
        }
        if tools:
            request["tools"] = tools
        if text:
            request["text"] = text
        if tool_choice is not None:
            request["tool_choice"] = tool_choice
        if include:
            request["include"] = include
        digest = hashlib.sha256(json.dumps(request, sort_keys=True, default=str).encode()).hexdigest()
        started = time.monotonic()
        try:
            response = self.client.responses.create(**request)
        except Exception as error:
            self._log(label, digest, None, 0.0, time.monotonic() - started, f"{type(error).__name__}: {error}")
            raise
        latency = time.monotonic() - started
        usage = response.usage.model_dump() if getattr(response, "usage", None) is not None else None
        cost = estimate_cost_usd(usage, self.pricing)
        self.ledger.add(cost)
        self._log(label, digest, usage, cost, latency, None, getattr(response, "id", None))
        return LlmResult(response, usage, cost, latency)

    def _log(self, label, digest, usage, cost, latency, error, response_id=None) -> None:
        if self.log_path is None:
            return
        entry = {
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "label": label,
            "model": self.config["model"],
            "request_sha256": digest,
            "response_id": response_id,
            "usage": usage,
            "cost_usd": cost,
            "latency_s": round(latency, 3),
            "error": error,
        }
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
