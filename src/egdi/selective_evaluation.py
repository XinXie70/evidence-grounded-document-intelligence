"""Deterministic risk-coverage evaluation for selective document answering."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any, Sequence


TARGET_COVERAGES = (1.0, 0.9, 0.8, 0.6)


def _validate(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    if not records:
        raise ValueError("at least one prediction record is required")
    seen: set[str] = set()
    validated = []
    for item in records:
        question_id = item.get("question_id")
        confidence = item.get("confidence")
        eligible = item.get("policy_eligible")
        task_correct = item.get("task_correct")
        grounded_correct = item.get("grounded_correct")
        if not isinstance(question_id, str) or not question_id or question_id in seen:
            raise ValueError("question_id values must be non-empty and unique")
        seen.add(question_id)
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise ValueError("confidence must be numeric")
        if not math.isfinite(float(confidence)):
            raise ValueError("confidence must be finite")
        if not isinstance(eligible, bool):
            raise ValueError("policy_eligible must be boolean")
        if not isinstance(task_correct, bool) or not isinstance(grounded_correct, bool):
            raise ValueError("task_correct and grounded_correct must be boolean")
        if grounded_correct and not task_correct:
            raise ValueError("grounded_correct cannot be true when task_correct is false")
        validated.append(
            {
                "question_id": question_id,
                "confidence": float(confidence),
                "policy_eligible": eligible,
                "task_correct": task_correct,
                "grounded_correct": grounded_correct,
            }
        )
    return validated


def _prefix_metrics(prefix: Sequence[dict[str, Any]], total: int) -> dict[str, Any]:
    answered = len(prefix)
    if answered == 0:
        return {
            "answered_count": 0,
            "coverage": 0.0,
            "selective_risk": None,
            "grounded_selective_risk": None,
        }
    errors = sum(not item["task_correct"] for item in prefix)
    grounded_errors = sum(not item["grounded_correct"] for item in prefix)
    return {
        "answered_count": answered,
        "coverage": answered / total,
        "selective_risk": errors / answered,
        "grounded_selective_risk": grounded_errors / answered,
    }


def _retention_point(
    prefix: Sequence[dict[str, Any]], *, total: int, eligible_total: int, target: float
) -> dict[str, Any]:
    return {
        "target_answer_retention": target,
        "answer_retention": len(prefix) / eligible_total if eligible_total else 0.0,
        **_prefix_metrics(prefix, total),
    }


def evaluate_risk_coverage(
    records: Sequence[dict[str, Any]],
    *,
    target_coverages: Sequence[float] = TARGET_COVERAGES,
) -> dict[str, Any]:
    """Evaluate confidence ordering and conservative tie-respecting operating points."""
    validated = _validate(records)
    if (
        not target_coverages
        or any(
            isinstance(target, bool)
            or not isinstance(target, (int, float))
            or not 0 < float(target) <= 1
            for target in target_coverages
        )
        or list(target_coverages) != sorted(set(target_coverages), reverse=True)
    ):
        raise ValueError("target_coverages must be unique, decreasing, and in (0, 1]")

    total = len(validated)
    eligible = sorted(
        (item for item in validated if item["policy_eligible"]),
        key=lambda item: (-item["confidence"], item["question_id"]),
    )
    curve = []
    for index in range(1, len(eligible) + 1):
        metrics = _prefix_metrics(eligible[:index], total)
        curve.append(
            {
                "rank": index,
                "question_id": eligible[index - 1]["question_id"],
                "confidence": eligible[index - 1]["confidence"],
                **metrics,
            }
        )

    tie_counts = Counter(item["confidence"] for item in eligible)
    tie_groups = []
    offset = 0
    for confidence in sorted(tie_counts, reverse=True):
        size = tie_counts[confidence]
        offset += size
        tie_groups.append(
            {
                "confidence": confidence,
                "question_count": size,
                "cumulative_answered_count": offset,
                "cumulative_coverage": offset / total,
                "cumulative_answer_retention": offset / len(eligible) if eligible else 0.0,
            }
        )

    operating_points = {}
    for target in target_coverages:
        allowed = [group for group in tie_groups if group["cumulative_coverage"] <= float(target)]
        if not allowed:
            operating_points[str(float(target))] = {
                "target_coverage": float(target),
                "confidence_threshold": None,
                **_prefix_metrics([], total),
            }
            continue
        boundary = allowed[-1]
        prefix = eligible[: boundary["cumulative_answered_count"]]
        operating_points[str(float(target))] = {
            "target_coverage": float(target),
            "confidence_threshold": boundary["confidence"],
            **_prefix_metrics(prefix, total),
        }


    retention_operating_points = {}
    for target in target_coverages:
        allowed = [
            group for group in tie_groups
            if group["cumulative_answer_retention"] <= float(target)
        ]
        if not allowed:
            retention_operating_points[str(float(target))] = {
                "confidence_threshold": None,
                **_retention_point([], total=total, eligible_total=len(eligible), target=float(target)),
            }
            continue
        boundary = allowed[-1]
        prefix = eligible[: boundary["cumulative_answered_count"]]
        retention_operating_points[str(float(target))] = {
            "confidence_threshold": boundary["confidence"],
            **_retention_point(
                prefix, total=total, eligible_total=len(eligible), target=float(target)
            ),
        }

    aurc = None if not curve else sum(item["selective_risk"] for item in curve) / len(curve)
    grounded_aurc = (
        None
        if not curve
        else sum(item["grounded_selective_risk"] for item in curve) / len(curve)
    )
    return {
        "question_count": total,
        "eligible_answer_count": len(eligible),
        "maximum_coverage": len(eligible) / total,
        "aurc_over_eligible_prefixes": aurc,
        "grounded_aurc_over_eligible_prefixes": grounded_aurc,
        "tie_break": "descending_confidence_then_question_id",
        "tie_groups": tie_groups,
        "operating_points": operating_points,
        "answer_retention_operating_points": retention_operating_points,
        "curve": curve,
    }
