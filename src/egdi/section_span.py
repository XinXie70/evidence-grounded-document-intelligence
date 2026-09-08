"""Deterministic section-span discovery for observed range-scoped questions."""

from __future__ import annotations

import re
from typing import Any, Sequence

from .text import PageRecord, tokenize_for_bm25


_SECTION_SCOPE_PATTERN = re.compile(
    r"\b(?:chapter|across\s+all\s+listed)\b",
    re.IGNORECASE,
)

_TITLE_STOPWORDS = {"and", "of", "the"}


def _validate_records(records: Sequence[PageRecord]) -> None:
    if not records:
        raise ValueError("at least one Page Record is required")
    if len({record.doc_id for record in records}) != 1:
        raise ValueError("all Page Records must belong to one document")
    if [record.page for record in records] != list(range(1, len(records) + 1)):
        raise ValueError("Page Records must be sequential from physical page 1")


def extract_top_level_sections(records: Sequence[PageRecord]) -> list[dict[str, Any]]:
    """Extract page-number-anchored top-level headings and their bounded spans."""
    _validate_records(records)
    starts: list[dict[str, Any]] = []
    for record in records:
        pattern = re.compile(
            rf"\b{record.page}\s+(\d+)\s+"
            r"([A-Z][A-Za-z]+(?:\s+(?:of|and|the|[A-Z][A-Za-z]+)){0,5})"
        )
        match = pattern.search(record.text[:320])
        if match is None:
            continue
        starts.append(
            {
                "start_page": record.page,
                "section_number": int(match.group(1)),
                "title": match.group(2).strip(),
            }
        )

    sections: list[dict[str, Any]] = []
    for index, start in enumerate(starts):
        end_page = starts[index + 1]["start_page"] - 1 if index + 1 < len(starts) else len(records)
        sections.append(
            {
                **start,
                "end_page": end_page,
                "pages": list(range(start["start_page"], end_page + 1)),
            }
        )
    return sections


def select_query_linked_section(
    question: str,
    records: Sequence[PageRecord],
    *,
    minimum_title_token_overlap: int = 2,
) -> dict[str, Any] | None:
    """Select one query-linked section only for an explicit range-scoped question."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a non-empty string")
    if (
        isinstance(minimum_title_token_overlap, bool)
        or not isinstance(minimum_title_token_overlap, int)
        or minimum_title_token_overlap < 1
    ):
        raise ValueError("minimum_title_token_overlap must be a positive integer")
    _validate_records(records)
    scope_match = _SECTION_SCOPE_PATTERN.search(question)
    if scope_match is None:
        return None

    question_tokens = set(tokenize_for_bm25(question))
    candidates: list[dict[str, Any]] = []
    for section in extract_top_level_sections(records):
        title_tokens = set(tokenize_for_bm25(section["title"])) - _TITLE_STOPWORDS
        overlap_tokens = sorted(question_tokens.intersection(title_tokens))
        if len(overlap_tokens) < minimum_title_token_overlap:
            continue
        candidates.append(
            {
                **section,
                "title_overlap_tokens": overlap_tokens,
                "title_overlap_count": len(overlap_tokens),
                "matched_scope_signal": scope_match.group(0).casefold(),
            }
        )
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item["title_overlap_count"], item["start_page"]))
    return candidates[0]
