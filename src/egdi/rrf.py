"""Deterministic Reciprocal Rank Fusion for page-retrieval artifacts."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

from .io import sha256_file, write_json
from .scoring import aggregate_page_scores, score_evidence_pages


DEFAULT_KS = (1, 3, 5, 10)
SLICE_FIELDS = ("page_span", "gold_text_status", "evidence_type", "extract_class")


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[int]], *, rank_constant: int = 60, top_k: int = 10
) -> list[tuple[int, float]]:
    """Fuse equally weighted rankings; ties resolve by ascending physical page ID."""
    if len(rankings) < 2:
        raise ValueError("RRF requires at least two rankings")
    if isinstance(rank_constant, bool) or not isinstance(rank_constant, int) or rank_constant < 1:
        raise ValueError("rank_constant must be a positive integer")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
        raise ValueError("top_k must be a positive integer")

    scores: dict[int, float] = {}
    for ranking in rankings:
        seen: set[int] = set()
        for rank, page in enumerate(ranking, start=1):
            if isinstance(page, bool) or not isinstance(page, int) or page < 1:
                raise ValueError("rankings must contain positive integer page IDs")
            if page in seen:
                raise ValueError("each input ranking must contain unique page IDs")
            seen.add(page)
            scores[page] = scores.get(page, 0.0) + 1.0 / (rank_constant + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:top_k]


def _question_map(run: dict[str, Any], label: str) -> dict[str, dict[str, Any]]:
    questions = run.get("per_question")
    if not isinstance(questions, list) or not questions:
        raise ValueError(f"{label}.per_question must be a non-empty list")
    result: dict[str, dict[str, Any]] = {}
    for question in questions:
        if not isinstance(question, dict):
            raise ValueError(f"{label}.per_question entries must be objects")
        question_id = question.get("question_id")
        if not isinstance(question_id, str) or not question_id:
            raise ValueError(f"{label} question_id must be a non-empty string")
        if question_id in result:
            raise ValueError(f"duplicate {label} question_id: {question_id}")
        result[question_id] = question
    return result


def _pages(question: dict[str, Any], field: str) -> list[int]:
    values = question.get(field)
    if not isinstance(values, list):
        raise ValueError(f"{field} must be a list")
    if any(isinstance(page, bool) or not isinstance(page, int) or page < 1 for page in values):
        raise ValueError(f"{field} must contain positive integer page IDs")
    if len(values) != len(set(values)):
        raise ValueError(f"{field} must not contain duplicate page IDs")
    return values


def _aggregate(results: Sequence[dict[str, Any]], ks: Sequence[int]) -> dict[str, Any]:
    return {
        str(k): aggregate_page_scores(
            [score_evidence_pages(result["gold_pages"], result["retrieved_pages"], k) for result in results]
        )
        for k in ks
    }


def evaluate_rrf_runs(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    rank_constant: int = 60,
    input_depth: int = 10,
    ks: Sequence[int] = DEFAULT_KS,
) -> dict[str, Any]:
    """Fuse matched retrieval artifacts without using gold labels in ranking."""
    if left.get("split") != "development_tune" or right.get("split") != "development_tune":
        raise ValueError("RRF tuning input must be development_tune")
    if not ks or any(isinstance(k, bool) or not isinstance(k, int) or k < 1 for k in ks):
        raise ValueError("ks must contain positive integers")
    if list(sorted(set(ks))) != list(ks):
        raise ValueError("ks must be unique and increasing")
    if isinstance(input_depth, bool) or not isinstance(input_depth, int) or input_depth < max(ks):
        raise ValueError("input_depth must be an integer at least as large as max(ks)")

    left_questions = _question_map(left, "left")
    right_questions = _question_map(right, "right")
    if set(left_questions) != set(right_questions):
        raise ValueError("retrieval runs must contain identical question IDs")

    per_question: list[dict[str, Any]] = []
    for question_id in left_questions:
        left_question = left_questions[question_id]
        right_question = right_questions[question_id]
        for field in ("question", "doc_id", "gold_pages", "slices"):
            if left_question.get(field) != right_question.get(field):
                raise ValueError(f"question metadata drift for {question_id}: {field}")
        gold_pages = _pages(left_question, "gold_pages")
        left_pages = _pages(left_question, "retrieved_pages")
        right_pages = _pages(right_question, "retrieved_pages")
        if len(left_pages) < input_depth or len(right_pages) < input_depth:
            raise ValueError(f"retrieval ranking shorter than input_depth for {question_id}")
        fused = reciprocal_rank_fusion(
            [left_pages[:input_depth], right_pages[:input_depth]],
            rank_constant=rank_constant,
            top_k=max(ks),
        )
        retrieved_pages = [page for page, _ in fused]
        per_question.append(
            {
                "question_id": question_id,
                "question": left_question["question"],
                "doc_id": left_question["doc_id"],
                "gold_pages": gold_pages,
                "retrieved_pages": retrieved_pages,
                "rrf_scores": [score for _, score in fused],
                "scores": {
                    str(k): score_evidence_pages(gold_pages, retrieved_pages, k).to_dict()
                    for k in ks
                },
                "slices": left_question["slices"],
            }
        )

    slices: dict[str, dict[str, Any]] = {}
    for field in SLICE_FIELDS:
        categories = sorted({result["slices"][field] for result in per_question})
        slices[field] = {
            category: _aggregate(
                [result for result in per_question if result["slices"][field] == category], ks
            )
            for category in categories
        }
    return {
        "schema_version": 1,
        "split": "development_tune",
        "question_count": len(per_question),
        "eligible_question_count": len(per_question),
        "excluded_question_count": left.get("excluded_question_count"),
        "exclusion_reasons": left.get("exclusion_reasons"),
        "aggregate": _aggregate(per_question, ks),
        "slices": slices,
        "per_question": per_question,
        "configuration": {
            "method": "reciprocal_rank_fusion",
            "rank_constant": rank_constant,
            "input_depth_per_retriever": input_depth,
            "weights": "equal",
            "tie_break": "ascending_physical_page_id",
            "top_ks": list(ks),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left", required=True, type=Path)
    parser.add_argument("--right", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {args.output}")
    left = json.loads(args.left.read_text(encoding="utf-8"))
    right = json.loads(args.right.read_text(encoding="utf-8"))
    config = json.loads(args.config.read_text(encoding="utf-8"))
    result = evaluate_rrf_runs(
        left,
        right,
        rank_constant=config["rank_constant"],
        input_depth=config["input_depth_per_retriever"],
        ks=config["top_ks"],
    )
    result["configuration"] = config
    result["input_sha256"] = {"left": sha256_file(args.left), "right": sha256_file(args.right)}
    result["configuration_sha256"] = sha256_file(args.config)
    write_json(args.output, result)
    print(
        json.dumps(
            {"output": str(args.output), "output_sha256": sha256_file(args.output), "aggregate": result["aggregate"]},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
