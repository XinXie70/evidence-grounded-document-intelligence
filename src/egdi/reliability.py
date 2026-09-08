"""Deterministic reliability and selective-answering outcome aggregation."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any, Iterable

from .io import sha256_file, write_json


ANSWERABLE = "answerable"
INSUFFICIENT_EVIDENCE = "insufficient_evidence"


def _required_bool(record: dict[str, Any], key: str) -> bool:
    value = record.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _safe_rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def classify_reliability_outcome(record: dict[str, Any]) -> dict[str, Any]:
    """Classify one audited response without using gold data as a policy signal."""
    question_id = record.get("question_id")
    if not isinstance(question_id, str) or not question_id:
        raise ValueError("question_id must be a non-empty string")
    benchmark_is_answerable = _required_bool(record, "benchmark_is_answerable")
    response_status = record.get("response_status")
    if response_status not in {ANSWERABLE, INSUFFICIENT_EVIDENCE}:
        raise ValueError("response_status must be answerable or insufficient_evidence")

    answer = record.get("answer")
    answered = response_status == ANSWERABLE
    if answered and (not isinstance(answer, str) or not answer.strip()):
        raise ValueError("answerable status requires a non-empty answer")
    if not answered and answer is not None:
        raise ValueError("insufficient_evidence status requires answer=null")

    answer_correct: bool | None = None
    grounded_correct: bool | None = None
    evidence_sufficient = record.get("evidence_sufficient")
    if evidence_sufficient is not None and not isinstance(evidence_sufficient, bool):
        raise ValueError("evidence_sufficient must be boolean or null")

    if answered:
        answer_correct = _required_bool(record, "answer_correct")
        grounded_correct = _required_bool(record, "grounded_correct")
        if grounded_correct and not answer_correct:
            raise ValueError("grounded_correct cannot be true when answer_correct is false")

    if not benchmark_is_answerable:
        if answered:
            outcome = "false_answer_on_unanswerable"
            benchmark_task_correct = False
            contextual_reliability_correct = False
            strict_grounded_task_correct = False
        else:
            outcome = "correct_abstention"
            benchmark_task_correct = True
            contextual_reliability_correct = True
            strict_grounded_task_correct = True
    elif answered:
        if answer_correct and grounded_correct:
            outcome = "grounded_success"
            contextual_reliability_correct = True
        elif answer_correct:
            outcome = "correct_answer_incomplete_grounding"
            contextual_reliability_correct = False
        else:
            outcome = "incorrect_answer"
            contextual_reliability_correct = False
        benchmark_task_correct = bool(answer_correct)
        strict_grounded_task_correct = bool(grounded_correct)
    else:
        if evidence_sufficient is None:
            raise ValueError(
                "answerable abstentions require an audited evidence_sufficient label"
            )
        if evidence_sufficient:
            outcome = "over_abstention"
            contextual_reliability_correct = False
        else:
            outcome = "appropriate_abstention_given_context"
            contextual_reliability_correct = True
        benchmark_task_correct = False
        strict_grounded_task_correct = False

    return {
        "question_id": question_id,
        "outcome": outcome,
        "answered": answered,
        "benchmark_is_answerable": benchmark_is_answerable,
        "evidence_sufficient": evidence_sufficient,
        "answer_correct": answer_correct,
        "grounded_correct": grounded_correct,
        "benchmark_task_correct": benchmark_task_correct,
        "strict_grounded_task_correct": strict_grounded_task_correct,
        "contextual_reliability_correct": contextual_reliability_correct,
    }


def aggregate_selective_metrics(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate one already-chosen answer/abstention policy over audited records."""
    outcomes = [classify_reliability_outcome(record) for record in records]
    if not outcomes:
        raise ValueError("at least one record is required")
    question_ids = [item["question_id"] for item in outcomes]
    if len(question_ids) != len(set(question_ids)):
        raise ValueError("question_id values must be unique")

    total = len(outcomes)
    answered = sum(item["answered"] for item in outcomes)
    answered_errors = sum(
        item["answered"] and item["answer_correct"] is not True for item in outcomes
    )
    answered_grounding_errors = sum(
        item["answered"] and item["grounded_correct"] is not True
        for item in outcomes
    )
    answerable = [item for item in outcomes if item["benchmark_is_answerable"]]
    unanswerable = [item for item in outcomes if not item["benchmark_is_answerable"]]
    sufficient_answerable = [
        item for item in answerable if item["evidence_sufficient"] is True
    ]
    insufficient_answerable = [
        item for item in answerable if item["evidence_sufficient"] is False
    ]

    return {
        "question_count": total,
        "answered_count": answered,
        "abstained_count": total - answered,
        "coverage": answered / total,
        "selective_risk": _safe_rate(answered_errors, answered),
        "grounded_selective_risk": _safe_rate(
            answered_grounding_errors, answered
        ),
        "benchmark_task_accuracy": sum(
            item["benchmark_task_correct"] for item in outcomes
        )
        / total,
        "strict_grounded_task_accuracy": sum(
            item["strict_grounded_task_correct"] for item in outcomes
        )
        / total,
        "contextual_reliability_accuracy": sum(
            item["contextual_reliability_correct"] for item in outcomes
        )
        / total,
        "unanswerable_false_answer_rate": _safe_rate(
            sum(item["answered"] for item in unanswerable), len(unanswerable)
        ),
        "answerable_abstention_rate": _safe_rate(
            sum(not item["answered"] for item in answerable), len(answerable)
        ),
        "over_abstention_rate_on_sufficient_answerable": _safe_rate(
            sum(not item["answered"] for item in sufficient_answerable),
            len(sufficient_answerable),
        ),
        "appropriate_abstention_rate_on_insufficient_context": _safe_rate(
            sum(not item["answered"] for item in insufficient_answerable),
            len(insufficient_answerable),
        ),
        "outcome_counts": dict(sorted(Counter(
            item["outcome"] for item in outcomes
        ).items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable output: {args.output}")
    records = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("input must be a JSON list")
    output = {
        "schema_version": 1,
        "input_path": str(args.input),
        "input_sha256": sha256_file(args.input),
        "records": [classify_reliability_outcome(record) for record in records],
        "metrics": aggregate_selective_metrics(records),
    }
    write_json(args.output, output)
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
