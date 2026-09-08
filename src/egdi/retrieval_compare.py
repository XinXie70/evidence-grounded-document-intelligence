"""Deterministic paired comparison of two evidence-page retrieval runs."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


OUTCOMES = ("both", "left_only", "right_only", "neither")
SLICE_FIELDS = ("evidence_type", "page_span", "gold_text_status", "extract_class")


def _positive_pages(values: object, field: str) -> list[int]:
    if not isinstance(values, list):
        raise ValueError(f"{field} must be a list")
    pages: list[int] = []
    seen: set[int] = set()
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{field} must contain positive integer page IDs")
        if value in seen:
            raise ValueError(f"{field} must not contain duplicate page IDs")
        pages.append(value)
        seen.add(value)
    return pages


def _question_map(run: dict[str, object], label: str) -> dict[str, dict[str, object]]:
    questions = run.get("per_question")
    if not isinstance(questions, list) or not questions:
        raise ValueError(f"{label}.per_question must be a non-empty list")
    mapped: dict[str, dict[str, object]] = {}
    for question in questions:
        if not isinstance(question, dict):
            raise ValueError(f"{label}.per_question entries must be objects")
        question_id = question.get("question_id")
        if not isinstance(question_id, str) or not question_id:
            raise ValueError(f"{label} question_id must be a non-empty string")
        if question_id in mapped:
            raise ValueError(f"duplicate {label} question_id: {question_id}")
        mapped[question_id] = question
    return mapped


def _outcome(left_success: bool, right_success: bool) -> str:
    if left_success and right_success:
        return "both"
    if left_success:
        return "left_only"
    if right_success:
        return "right_only"
    return "neither"


def _deduplicated_union(left: Iterable[int], right: Iterable[int]) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    for page in (*left, *right):
        if page not in seen:
            result.append(page)
            seen.add(page)
    return result


def compare_retrieval_runs(
    left: dict[str, object],
    right: dict[str, object],
    *,
    left_label: str,
    right_label: str,
    ks: tuple[int, ...] = (1, 3, 5, 10),
) -> dict[str, object]:
    """Compare matched runs and report individual success plus union-pool coverage."""
    if not left_label or not right_label or left_label == right_label:
        raise ValueError("comparison labels must be non-empty and distinct")
    if not ks or any(isinstance(k, bool) or not isinstance(k, int) or k < 1 for k in ks):
        raise ValueError("ks must contain positive integers")
    if tuple(sorted(set(ks))) != ks:
        raise ValueError("ks must be unique and increasing")
    if left.get("split") != right.get("split"):
        raise ValueError("retrieval runs must use the same split")

    left_questions = _question_map(left, "left")
    right_questions = _question_map(right, "right")
    if set(left_questions) != set(right_questions):
        raise ValueError("retrieval runs must contain identical question IDs")

    paired: list[dict[str, object]] = []
    for question_id in sorted(left_questions):
        left_question = left_questions[question_id]
        right_question = right_questions[question_id]
        for field in ("question", "doc_id", "slices"):
            if left_question.get(field) != right_question.get(field):
                raise ValueError(f"question metadata drift for {question_id}: {field}")
        left_gold = _positive_pages(left_question.get("gold_pages"), "gold_pages")
        right_gold = _positive_pages(right_question.get("gold_pages"), "gold_pages")
        if left_gold != right_gold:
            raise ValueError(f"gold-page drift for {question_id}")
        left_pages = _positive_pages(left_question.get("retrieved_pages"), "retrieved_pages")
        right_pages = _positive_pages(right_question.get("retrieved_pages"), "retrieved_pages")
        paired.append(
            {
                "question_id": question_id,
                "question": left_question.get("question"),
                "doc_id": left_question.get("doc_id"),
                "gold_pages": left_gold,
                "left_pages": left_pages,
                "right_pages": right_pages,
                "slices": left_question.get("slices"),
            }
        )

    comparisons: dict[str, object] = {}
    for k in ks:
        outcome_counts = {
            "any_evidence_recall": Counter(),
            "complete_evidence_recall": Counter(),
        }
        union_any = 0
        union_complete = 0
        union_true_positive = 0
        gold_page_count = 0
        pool_sizes: list[int] = []
        for question in paired:
            gold = set(question["gold_pages"])
            left_pages = question["left_pages"][:k]
            right_pages = question["right_pages"][:k]
            left_hits = gold.intersection(left_pages)
            right_hits = gold.intersection(right_pages)
            union_pages = _deduplicated_union(left_pages, right_pages)
            union_hits = gold.intersection(union_pages)
            outcome_counts["any_evidence_recall"][_outcome(bool(left_hits), bool(right_hits))] += 1
            outcome_counts["complete_evidence_recall"][
                _outcome(left_hits == gold, right_hits == gold)
            ] += 1
            union_any += bool(union_hits)
            union_complete += union_hits == gold
            union_true_positive += len(union_hits)
            gold_page_count += len(gold)
            pool_sizes.append(len(union_pages))
        comparisons[str(k)] = {
            "outcomes": {
                metric: {outcome: counts[outcome] for outcome in OUTCOMES}
                for metric, counts in outcome_counts.items()
            },
            "union_candidate_pool": {
                "any_evidence_recall": union_any / len(paired),
                "complete_evidence_recall": union_complete / len(paired),
                "micro_evidence_page_recall": union_true_positive / gold_page_count,
                "mean_unique_pages": sum(pool_sizes) / len(pool_sizes),
                "maximum_unique_pages": max(pool_sizes),
            },
        }

    analysis_k = ks[-1]
    slice_counts: dict[str, dict[str, dict[str, Counter[str]]]] = {}
    per_question: list[dict[str, object]] = []
    for metric in ("any_evidence_recall", "complete_evidence_recall"):
        slice_counts[metric] = {
            outcome: {field: Counter() for field in SLICE_FIELDS} for outcome in OUTCOMES
        }
    for question in paired:
        gold = set(question["gold_pages"])
        left_hits = gold.intersection(question["left_pages"][:analysis_k])
        right_hits = gold.intersection(question["right_pages"][:analysis_k])
        outcomes = {
            "any_evidence_recall": _outcome(bool(left_hits), bool(right_hits)),
            "complete_evidence_recall": _outcome(left_hits == gold, right_hits == gold),
        }
        slices = question["slices"]
        if not isinstance(slices, dict):
            raise ValueError(f"slices must be an object for {question['question_id']}")
        for metric, outcome in outcomes.items():
            for field in SLICE_FIELDS:
                value = slices.get(field)
                if not isinstance(value, str) or not value:
                    raise ValueError(f"missing slice {field} for {question['question_id']}")
                slice_counts[metric][outcome][field][value] += 1
        per_question.append(
            {
                **question,
                "analysis_k": analysis_k,
                "outcomes": outcomes,
                "union_pages": _deduplicated_union(
                    question["left_pages"][:analysis_k], question["right_pages"][:analysis_k]
                ),
            }
        )

    return {
        "schema_version": 1,
        "split": left.get("split"),
        "left_label": left_label,
        "right_label": right_label,
        "question_count": len(paired),
        "ks": list(ks),
        "comparisons": comparisons,
        "slice_counts_at_max_k": {
            metric: {
                outcome: {
                    field: dict(sorted(counter.items()))
                    for field, counter in fields.items()
                }
                for outcome, fields in outcomes.items()
            }
            for metric, outcomes in slice_counts.items()
        },
        "per_question": per_question,
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left", required=True, type=Path)
    parser.add_argument("--right", required=True, type=Path)
    parser.add_argument("--left-label", required=True)
    parser.add_argument("--right-label", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {args.output}")
    left = json.loads(args.left.read_text(encoding="utf-8"))
    right = json.loads(args.right.read_text(encoding="utf-8"))
    result = compare_retrieval_runs(
        left, right, left_label=args.left_label, right_label=args.right_label
    )
    result["input_sha256"] = {"left": _sha256(args.left), "right": _sha256(args.right)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "sha256": _sha256(args.output)}, indent=2))


if __name__ == "__main__":
    main()
