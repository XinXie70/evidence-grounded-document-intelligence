"""Fixed pipelines: retrieve once, read the top pages, answer or abstain in one call."""

from __future__ import annotations

import json
from typing import Any

from .answer import ANSWER_RULES, RESPONSE_SCHEMA, normalize_final, validate_final
from .llm import BudgetExceeded, LlmClient, json_schema_format
from .tools import MAX_PAGE_CHARS

# B0 is the V1-style baseline; B1 only reads more pages (isolates "read more" from "search more").
PAGE_BUDGETS = {"B0": 3, "B1": 6}

INSTRUCTIONS = "You answer a question about one PDF document. " + ANSWER_RULES


def render_input(question: str, pages: dict[int, str]) -> str:
    sections = [f"Question:\n{question}", "Document pages:"]
    sections += [f"[Physical PDF page {page}]\n{text}" for page, text in pages.items()]
    return "\n\n".join(sections)


def run_baseline(system: str, question: str, document: Any, llm: LlmClient, label: str) -> dict[str, Any]:
    """Run B0/B1 on one question; model or parsing failures are recorded, not raised."""
    hits = document.search(question, PAGE_BUDGETS[system])
    pages = {hit["page"]: document.page_text[hit["page"]][:MAX_PAGE_CHARS] for hit in hits}
    result: dict[str, Any] = {
        "system": system,
        "retrieved_pages": list(pages),
        "final": None,
        "validation_errors": [],
        "error": None,
        "usage": None,
        "cost_usd": 0.0,
        "latency_s": 0.0,
        "response_id": None,
    }
    try:
        reply = llm.respond(
            label=label,
            input=render_input(question, pages),
            instructions=INSTRUCTIONS,
            text=json_schema_format("document_answer", RESPONSE_SCHEMA),
        )
    except BudgetExceeded:
        raise
    except Exception as error:  # API failure: keep the record, let the caller decide
        result["error"] = f"{type(error).__name__}: {error}"
        return result
    result.update(
        usage=reply.usage,
        cost_usd=reply.cost_usd,
        latency_s=round(reply.latency_s, 3),
        response_id=getattr(reply.response, "id", None),
    )
    try:
        parsed = json.loads(reply.response.output_text)
        if not isinstance(parsed, dict):
            raise ValueError("model output is not a JSON object")
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        result["error"] = f"unparseable output: {error}"
        return result
    final = normalize_final(parsed)
    result["final"] = final
    result["validation_errors"] = validate_final(final, list(pages))
    return result
