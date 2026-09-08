"""Label-free document text-quality signals for retrieval routing."""

from __future__ import annotations

import unicodedata
from typing import Sequence

from .text import PageRecord


GARBLED_CONTROL_CHARACTER_RATIO_THRESHOLD = 0.05


def control_character_ratio(records: Sequence[PageRecord]) -> float:
    """Return the share of non-whitespace characters classified as Unicode controls."""
    if not records:
        raise ValueError("at least one Page Record is required")
    doc_ids = {record.doc_id for record in records}
    if len(doc_ids) != 1:
        raise ValueError("all Page Records must belong to one document")

    non_whitespace_count = 0
    control_count = 0
    for record in records:
        for character in record.text:
            if character.isspace():
                continue
            non_whitespace_count += 1
            control_count += unicodedata.category(character) == "Cc"

    if non_whitespace_count == 0:
        return 0.0
    return control_count / non_whitespace_count


def has_garbled_native_text(
    records: Sequence[PageRecord],
    *,
    threshold: float = GARBLED_CONTROL_CHARACTER_RATIO_THRESHOLD,
) -> bool:
    """Flag the observed embedded-font failure without using labels or answers."""
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise TypeError("threshold must be a number")
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0 and 1")
    return control_character_ratio(records) > threshold
