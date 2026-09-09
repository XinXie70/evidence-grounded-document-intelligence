"""Parse reusable arithmetic intent from comparison-question wording."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re


_DIRECTIONAL = re.compile(
    r"\b(more|greater|higher|larger|fewer|less|lower)\b.*"
    r"\b(than|compared\s+to)\b",
    re.IGNORECASE,
)
_ABSOLUTE_DIFFERENCE = re.compile(r"\b(?:what|how much)\b.*\bdifference\b.*\bbetween\b", re.IGNORECASE)
_TRAILING_DIFFERENCE_AFTER_COMPARISON = re.compile(
    r"\bcompared\s+to\b.*\bwhat\s+is\s+the\s+difference\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ComparisonIntent:
    operation: str
    wording_family: str
    direction_word: str | None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


def parse_comparison_intent(question: str) -> ComparisonIntent:
    """Recognize arithmetic intent without interpreting domain-specific facts."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a non-empty string")
    if (
        _ABSOLUTE_DIFFERENCE.search(question)
        or _TRAILING_DIFFERENCE_AFTER_COMPARISON.search(question)
    ):
        return ComparisonIntent(
            operation="absolute_difference",
            wording_family="difference_between",
            direction_word=None,
        )
    directional = _DIRECTIONAL.search(question)
    if directional:
        direction = directional.group(1).casefold()
        return ComparisonIntent(
            operation="left_minus_right",
            wording_family="directional_comparison",
            direction_word=direction,
        )
    raise ValueError("question does not express a supported comparison intent")
