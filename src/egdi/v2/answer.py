"""The final-answer format shared by the fixed baselines and the agent."""

from __future__ import annotations

from typing import Any

ANSWERED = "answered"
INSUFFICIENT = "insufficient_evidence"

ANSWER_RULES = (
    "Answer using only the document pages you have been given. Give the answer directly and "
    "concisely, with units where the question implies them. If the pages do not adequately "
    "support an answer, say so: status='insufficient_evidence', answer=null and no cited pages. "
    "Otherwise status='answered' and cite the 1-based physical PDF page numbers that support the "
    "answer. Cite only pages you were given."
)

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "answer", "cited_pages"],
    "properties": {
        "status": {"type": "string", "enum": [ANSWERED, INSUFFICIENT]},
        "answer": {"type": ["string", "null"]},
        "cited_pages": {"type": "array", "items": {"type": "integer", "minimum": 1}},
    },
}


def normalize_final(raw: dict[str, Any]) -> dict[str, Any]:
    """Canonical form: an insufficient-evidence result carries no answer and no citations."""
    status = raw.get("status")
    pages = raw.get("cited_pages")
    pages = sorted({p for p in pages if isinstance(p, int) and not isinstance(p, bool)}) if isinstance(pages, list) else []
    answer = raw.get("answer")
    answer = answer.strip() if isinstance(answer, str) else None
    if status == INSUFFICIENT:
        return {"status": INSUFFICIENT, "answer": None, "cited_pages": []}
    return {"status": status, "answer": answer, "cited_pages": pages}


def validate_final(final: dict[str, Any], supplied_pages: list[int]) -> list[str]:
    """Return the list of contract violations (empty when the result is well formed)."""
    errors: list[str] = []
    if final["status"] not in (ANSWERED, INSUFFICIENT):
        return ["status is invalid"]
    if final["status"] == ANSWERED:
        if not final["answer"]:
            errors.append("answered result has no answer")
        if not final["cited_pages"]:
            errors.append("answered result cites no page")
    outside = sorted(set(final["cited_pages"]) - set(supplied_pages))
    if outside:
        errors.append(f"cited pages were not supplied: {outside}")
    return errors
