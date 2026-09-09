"""Deterministic arithmetic and polarity checks for explicit comparison answers."""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import json
import re
from pathlib import Path
from typing import Any, Sequence

from .io import sha256_file, write_json


_NUMBER = re.compile(r"(?<![A-Za-z0-9])[-+]?\d+(?:\.\d+)?")
_DECIMAL_VALUE = re.compile(
    r"[-+]?(?:(?:\d+)|(?:\d{1,3}(?:,\d{3})+))(?:\.\d+)?"
)
_ACCOUNTING_DECIMAL_VALUE = re.compile(
    r"\((?:(?:\d+)|(?:\d{1,3}(?:,\d{3})+))(?:\.\d+)?\)"
)
_MORE = re.compile(r"\b(?:more|greater|higher|larger)\b", re.IGNORECASE)
_FEWER = re.compile(r"\b(?:fewer|less|lower)\b", re.IGNORECASE)
_DIRECTIONAL_QUESTION = re.compile(
    r"\b(?:more|greater|higher|larger|fewer|less|lower)\b.*"
    r"\b(?:than|compared\s+to)\b",
    re.IGNORECASE,
)


def parse_decimal_value(value: str) -> Decimal:
    """Parse a finite decimal with grouped commas or accounting parentheses."""
    if not isinstance(value, str):
        raise ValueError("fact value must be a decimal string")
    stripped = value.strip()
    if _ACCOUNTING_DECIMAL_VALUE.fullmatch(stripped):
        normalized = "-" + stripped[1:-1].replace(",", "")
    elif _DECIMAL_VALUE.fullmatch(stripped):
        normalized = stripped.replace(",", "")
    else:
        raise ValueError("fact value must be a decimal string")
    try:
        number = Decimal(normalized)
    except (InvalidOperation, TypeError) as error:
        raise ValueError("fact value must be a decimal string") from error
    if not number.is_finite():
        raise ValueError("fact value must be a finite decimal string")
    return number


def _decimal_text(value: Decimal) -> str:
    """Render audit values in plain decimal notation for human inspection."""
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return "0" if rendered in {"-0", ""} else rendered


def _normalized_hours(value: str, unit: str) -> Decimal:
    number = parse_decimal_value(value)
    normalized_unit = unit.casefold().strip()
    if normalized_unit in {"hour", "hours"}:
        return number
    if normalized_unit in {"minute", "minutes"}:
        return number / Decimal(60)
    raise ValueError("fact unit must be hours or minutes")


def _normalize_pair(
    left_value: str, left_unit: str, right_value: str, right_unit: str
) -> tuple[Decimal, Decimal, str]:
    """Normalize convertible time units or preserve one shared count unit."""
    normalized_left_unit = left_unit.casefold().strip()
    normalized_right_unit = right_unit.casefold().strip()
    time_units = {"hour", "hours", "minute", "minutes"}
    if normalized_left_unit in time_units and normalized_right_unit in time_units:
        return (
            _normalized_hours(left_value, left_unit),
            _normalized_hours(right_value, right_unit),
            "hours",
        )
    canonical_left = normalized_left_unit.rstrip("s")
    canonical_right = normalized_right_unit.rstrip("s")
    if canonical_left != canonical_right or not canonical_left:
        raise ValueError("fact units must be convertible time units or the same count unit")
    if normalized_left_unit == normalized_right_unit:
        shared_unit = normalized_left_unit
    else:
        shared_unit = (
            normalized_left_unit
            if normalized_left_unit.endswith("s")
            else normalized_right_unit
        )
    return parse_decimal_value(left_value), parse_decimal_value(right_value), shared_unit


def _fact_value_and_unit(fact: dict[str, Any]) -> tuple[str, str]:
    value = fact.get("value")
    unit = fact.get("unit")
    if not isinstance(value, str) or not isinstance(unit, str):
        raise ValueError("each fact must contain string value and unit fields")
    return value, unit


def compute_comparison(selected_facts: Sequence[dict[str, Any]]) -> dict[str, str]:
    """Compute the deterministic relation for two ordered evidence facts."""
    if len(selected_facts) != 2:
        raise ValueError("comparison requires exactly two ordered facts")
    left_value, left_unit = _fact_value_and_unit(selected_facts[0])
    right_value, right_unit = _fact_value_and_unit(selected_facts[1])
    left, right, unit = _normalize_pair(left_value, left_unit, right_value, right_unit)
    difference = left - right
    return {
        "left_operand": _decimal_text(left),
        "right_operand": _decimal_text(right),
        "signed_difference": _decimal_text(difference),
        "magnitude": _decimal_text(abs(difference)),
        "unit": unit,
        "direction": "more" if difference > 0 else "fewer" if difference < 0 else "equal",
    }


def check_comparison_consistency(
    question: str,
    selected_facts: Sequence[dict[str, Any]],
    model_output: dict[str, Any],
    *,
    numeric_tolerance: Decimal = Decimal("0.01"),
) -> dict[str, Any]:
    """Reject an answer when magnitude or comparative direction contradicts facts."""
    if not isinstance(question, str) or not _DIRECTIONAL_QUESTION.search(question):
        raise ValueError("checker requires an explicit directional comparison question")
    if len(selected_facts) != 2:
        raise ValueError("checker requires exactly two ordered comparison facts")
    if numeric_tolerance < 0:
        raise ValueError("numeric_tolerance cannot be negative")

    comparison = compute_comparison(selected_facts)
    left_normalized = Decimal(comparison["left_operand"])
    right_normalized = Decimal(comparison["right_operand"])
    signed_difference = Decimal(comparison["signed_difference"])
    magnitude = Decimal(comparison["magnitude"])
    normalized_unit = comparison["unit"]
    expected_direction = comparison["direction"]

    answer = model_output.get("answer")
    status = model_output.get("status")
    if status != "answerable" or not isinstance(answer, str) or not answer.strip():
        unavailable = {
            "accepted": False,
            "reason": "answer_is_not_available_for_consistency_check",
            "expected_direction": expected_direction,
            "expected_magnitude": _decimal_text(magnitude),
            "normalized_unit": normalized_unit,
        }
        if normalized_unit == "hours":
            unavailable["expected_magnitude_hours"] = _decimal_text(magnitude)
        return unavailable

    answer_numbers = []
    for match in _NUMBER.finditer(answer):
        try:
            answer_numbers.append(Decimal(match.group(0)))
        except InvalidOperation:
            continue
    magnitude_correct = any(
        abs(abs(number) - magnitude) <= numeric_tolerance for number in answer_numbers
    )
    contains_more = bool(_MORE.search(answer))
    contains_fewer = bool(_FEWER.search(answer))
    if expected_direction == "more":
        direction_correct = contains_more and not contains_fewer
    elif expected_direction == "fewer":
        direction_correct = contains_fewer and not contains_more
    else:
        direction_correct = not contains_more and not contains_fewer

    accepted = magnitude_correct and direction_correct
    reasons = []
    if not magnitude_correct:
        reasons.append("numeric_magnitude_mismatch")
    if not direction_correct:
        reasons.append("comparative_polarity_mismatch")
    result = {
        "accepted": accepted,
        "reason": "consistent" if accepted else ";".join(reasons),
        "left_operand": _decimal_text(left_normalized),
        "right_operand": _decimal_text(right_normalized),
        "signed_difference": _decimal_text(signed_difference),
        "expected_magnitude": _decimal_text(magnitude),
        "normalized_unit": normalized_unit,
        "expected_direction": expected_direction,
        "observed_contains_more": contains_more,
        "observed_contains_fewer": contains_fewer,
        "numeric_magnitude_correct": magnitude_correct,
        "comparative_direction_correct": direction_correct,
        "policy_action": "accept" if accepted else "reject_and_abstain_or_regenerate",
    }
    if normalized_unit == "hours":
        result.update(
            {
                "left_operand_hours": _decimal_text(left_normalized),
                "right_operand_hours": _decimal_text(right_normalized),
                "signed_difference_hours": _decimal_text(signed_difference),
                "expected_magnitude_hours": _decimal_text(magnitude),
            }
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable audit: {args.output}")
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    result = json.loads(args.result.read_text(encoding="utf-8"))
    if selection.get("question_id") != result.get("question_id"):
        raise ValueError("selection and result question ids must match")
    audit = {
        "schema_version": 1,
        "experiment_type": "deterministic_comparison_consistency_audit",
        "question_id": result["question_id"],
        "check": check_comparison_consistency(
            selection["question"], selection["selected_facts"], result["output"]
        ),
        "selection_sha256": sha256_file(args.selection),
        "result_sha256": sha256_file(args.result),
        "paid_api_used": False,
    }
    write_json(args.output, audit)
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
