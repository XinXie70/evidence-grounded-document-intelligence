"""Deterministic, label-free routing signals for text and visual document paths."""

from __future__ import annotations

import re
from typing import Any, Sequence

from .text import PageRecord


ROUTE_TEXT = "r0_text"
ROUTE_LOCAL_VISUAL = "r1_local_visual"
ROUTE_SCANNED_DOCUMENT = "r2_scanned_document"
ROUTE_DOCUMENT_GLOBAL = "r3_document_global"

_GLOBAL_PATTERNS = (
    re.compile(r"\bacross\s+the\s+entire\s+document\b", re.IGNORECASE),
    re.compile(r"\bthroughout\s+the\s+(?:entire\s+)?document\b", re.IGNORECASE),
    re.compile(r"\bin\s+the\s+(?:entire|whole)\s+document\b", re.IGNORECASE),
    re.compile(r"\bacross\s+all\s+pages\b", re.IGNORECASE),
)

_VISUAL_PATTERN = re.compile(
    r"\b(?:bar\s+chart|chart|figure|diagram|graph|image|illustration|map|table)\b",
    re.IGNORECASE,
)


def choose_visual_route(
    question: str, records: Sequence[PageRecord]
) -> dict[str, Any]:
    """Choose one routing hypothesis using only inference-time observable signals."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a non-empty string")
    if not records:
        raise ValueError("at least one Page Record is required")
    doc_ids = {record.doc_id for record in records}
    if len(doc_ids) != 1:
        raise ValueError("all Page Records must belong to one document")
    pages = [record.page for record in records]
    if len(pages) != len(set(pages)):
        raise ValueError("Page Records must have unique physical page numbers")

    nonempty_page_count = sum(bool(record.text.strip()) for record in records)
    document_page_count = len(records)
    text_coverage_ratio = nonempty_page_count / document_page_count
    global_match = next(
        (pattern.search(question).group(0) for pattern in _GLOBAL_PATTERNS if pattern.search(question)),
        None,
    )
    visual_match = _VISUAL_PATTERN.search(question)

    if global_match is not None:
        route = ROUTE_DOCUMENT_GLOBAL
        reason = "question_requires_document_complete_coverage"
        matched_signal = global_match.casefold()
    elif nonempty_page_count == 0:
        route = ROUTE_SCANNED_DOCUMENT
        reason = "document_has_zero_native_text_pages"
        matched_signal = "zero_native_text_pages"
    elif visual_match is not None:
        route = ROUTE_LOCAL_VISUAL
        reason = "question_explicitly_mentions_visual_structure"
        matched_signal = visual_match.group(0).casefold()
    else:
        route = ROUTE_TEXT
        reason = "no_observed_visual_or_global_trigger"
        matched_signal = None

    return {
        "schema_version": 1,
        "route": route,
        "reason": reason,
        "matched_signal": matched_signal,
        "document_page_count": document_page_count,
        "nonempty_page_count": nonempty_page_count,
        "text_coverage_ratio": text_coverage_ratio,
        "uses_gold_or_answer_labels": False,
    }
