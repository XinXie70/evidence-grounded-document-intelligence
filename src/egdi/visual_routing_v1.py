"""Versioned routing extension for an observed document-global wording gap."""

from __future__ import annotations

import re
from typing import Any, Sequence

from .text import PageRecord
from .visual_routing import ROUTE_DOCUMENT_GLOBAL, choose_visual_route


ROUTING_POLICY_VERSION = "r0-r3-v1"

_ACROSS_DOCUMENT_PATTERN = re.compile(
    r"\bacross\s+the\s+document\b",
    re.IGNORECASE,
)


def choose_visual_route_v1(
    question: str, records: Sequence[PageRecord]
) -> dict[str, Any]:
    """Apply v0 routing plus the tune-observed `across the document` signal."""
    result = choose_visual_route(question, records)
    match = _ACROSS_DOCUMENT_PATTERN.search(question)
    if match is not None:
        result = {
            **result,
            "route": ROUTE_DOCUMENT_GLOBAL,
            "reason": "question_requires_document_complete_coverage",
            "matched_signal": match.group(0).casefold(),
        }
    return {**result, "routing_policy_version": ROUTING_POLICY_VERSION}
