"""Conservative text normalization for deterministic retrieval baselines."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass


_WHITESPACE = re.compile(r"\s+")
_BM25_TOKEN = re.compile(r"[^\W_]+", flags=re.UNICODE)

TEXT_LAYER_MISSING_MAX_CHARS = 19
LOW_TEXT_MAX_CHARS = 99


@dataclass(frozen=True)
class PageRecord:
    """One reversible, page-bounded retrieval record."""

    doc_id: str
    page: int
    text: str
    non_whitespace_chars: int
    extraction_status: str

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


def normalize_whitespace(text: str) -> str:
    """Collapse consecutive Unicode whitespace without deleting content.

    The v0 baseline deliberately preserves case, punctuation, numbers, headings,
    headers, footers, and printed page numbers. Page identity is stored separately
    as metadata rather than inferred from page text.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    return _WHITESPACE.sub(" ", text).strip()


def tokenize_for_bm25(text: str) -> list[str]:
    """Tokenize letters and numbers for the v0 lexical baseline.

    Case is folded for matching; punctuation and underscores are boundaries. Stopwords,
    numbers, and repeated terms are retained. The stored Page Record text is not modified.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    return [match.group(0).casefold() for match in _BM25_TOKEN.finditer(text)]


def classify_text_layer(non_whitespace_chars: int) -> str:
    """Classify page text using the thresholds frozen during Day 1."""
    if isinstance(non_whitespace_chars, bool) or not isinstance(non_whitespace_chars, int):
        raise TypeError("non_whitespace_chars must be an integer")
    if non_whitespace_chars < 0:
        raise ValueError("non_whitespace_chars cannot be negative")
    if non_whitespace_chars <= TEXT_LAYER_MISSING_MAX_CHARS:
        return "text_layer_missing"
    if non_whitespace_chars <= LOW_TEXT_MAX_CHARS:
        return "low_text"
    return "ok"


def build_page_record(doc_id: str, page: int, raw_text: str) -> PageRecord:
    """Normalize one physical PDF page while preserving its source identity."""
    if not isinstance(doc_id, str) or not doc_id.strip():
        raise ValueError("doc_id must be a non-empty string")
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise ValueError("page must be a positive integer using 1-based PDF page numbering")
    normalized = normalize_whitespace(raw_text)
    char_count = sum(not character.isspace() for character in raw_text)
    return PageRecord(
        doc_id=doc_id,
        page=page,
        text=normalized,
        non_whitespace_chars=char_count,
        extraction_status=classify_text_layer(char_count),
    )
