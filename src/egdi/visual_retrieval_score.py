"""Score frozen blind visual rankings against the source RRF run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .io import sha256_file, write_json
from .scoring import aggregate_page_scores, score_evidence_pages


EVALUATION_KS = (1, 3, 5, 10)


def _positive_unique_pages(value: Any, field: str) -> list[int]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be a non-empty list")
    if any(isinstance(page, bool) or not isinstance(page, int) or page < 1 for page in value):
        raise ValueError(f"{field} must contain positive integers")
    if len(value) != len(set(value)):
        raise ValueError(f"{field} must contain unique pages")
    return value


def _aggregate(items: Sequence[dict[str, Any]], field: str) -> dict[str, Any]:
    if not items:
        raise ValueError("cannot aggregate an empty question slice")
    return {
        str(k): aggregate_page_scores(
            [score_evidence_pages(item["gold_pages"], item[field], k) for item in items]
        )
        for k in EVALUATION_KS
    }


def _success_count(items: Sequence[dict[str, Any]], field: str, metric: str, k: int) -> int:
    return sum(
        int(getattr(score_evidence_pages(item["gold_pages"], item[field], k), metric))
        for item in items
    )


def _paired_outcome(original: float, visual: float) -> str:
    if original == visual:
        return "both_success" if original == 1.0 else "both_failure"
    return "visual_gain" if visual == 1.0 else "visual_loss"


def score_visual_rankings(
    blind_run: dict[str, Any], rrf_run: dict[str, Any]
) -> dict[str, Any]:
    """Join by question ID only after rankings are frozen, then score both orders."""
    if blind_run.get("split") != "development_tune" or rrf_run.get("split") != "development_tune":
        raise ValueError("visual scoring is restricted to development_tune")
    if blind_run.get("status") != "blind_visual_rankings_frozen_before_scoring":
        raise ValueError("blind rankings are not marked frozen")
    if blind_run.get("contains_gold_or_answer_labels") is not False:
        raise ValueError("blind rankings must explicitly exclude evaluation labels")

    source = rrf_run.get("per_question")
    rankings = blind_run.get("rankings")
    if not isinstance(source, list) or not source or not isinstance(rankings, list) or not rankings:
        raise ValueError("both inputs must contain non-empty question records")
    source_by_id: dict[str, dict[str, Any]] = {}
    for item in source:
        question_id = item.get("question_id")
        if not isinstance(question_id, str) or not question_id or question_id in source_by_id:
            raise ValueError("source RRF question IDs must be non-empty and unique")
        source_by_id[question_id] = item

    evaluated: list[dict[str, Any]] = []
    seen: set[str] = set()
    candidate_depth = 10
    for ranking in rankings:
        question_id = ranking.get("question_id")
        if not isinstance(question_id, str) or question_id in seen:
            raise ValueError("blind ranking question IDs must be non-empty and unique")
        seen.add(question_id)
        if question_id not in source_by_id:
            raise ValueError(f"blind question is absent from source RRF run: {question_id}")
        source_item = source_by_id[question_id]
        if ranking.get("doc_id") != source_item.get("doc_id"):
            raise ValueError(f"document provenance drift: {question_id}")
        original = _positive_unique_pages(ranking.get("original_rrf_pages"), "original_rrf_pages")
        visual = _positive_unique_pages(ranking.get("visual_reranked_pages"), "visual_reranked_pages")
        expected = _positive_unique_pages(source_item.get("retrieved_pages"), "retrieved_pages")[:candidate_depth]
        gold = _positive_unique_pages(source_item.get("gold_pages"), "gold_pages")
        if original != expected:
            raise ValueError(f"frozen RRF candidate order drift: {question_id}")
        if set(visual) != set(original):
            raise ValueError(f"visual ranking changed the candidate-page set: {question_id}")
        slices = source_item.get("slices")
        if not isinstance(slices, dict) or slices.get("page_span") not in {"single", "multi"}:
            raise ValueError(f"missing frozen page_span slice: {question_id}")
        scores = {
            str(k): {
                "original_rrf": score_evidence_pages(gold, original, k).to_dict(),
                "visual_rerank": score_evidence_pages(gold, visual, k).to_dict(),
            }
            for k in EVALUATION_KS
        }
        for k in EVALUATION_KS:
            scores[str(k)]["paired_outcome"] = {
                metric: _paired_outcome(
                    scores[str(k)]["original_rrf"][metric],
                    scores[str(k)]["visual_rerank"][metric],
                )
                for metric in ("any_evidence_recall", "complete_evidence_recall")
            }
        evaluated.append(
            {
                "question_id": question_id,
                "doc_id": source_item["doc_id"],
                "gold_pages": gold,
                "original_rrf_pages": original,
                "visual_reranked_pages": visual,
                "page_span": slices["page_span"],
                "scores": scores,
            }
        )

    original_aggregate = _aggregate(evaluated, "original_rrf_pages")
    visual_aggregate = _aggregate(evaluated, "visual_reranked_pages")
    paired_counts: dict[str, Any] = {}
    for k in EVALUATION_KS:
        paired_counts[str(k)] = {}
        for metric in ("any_evidence_recall", "complete_evidence_recall"):
            original_count = _success_count(evaluated, "original_rrf_pages", metric, k)
            visual_count = _success_count(evaluated, "visual_reranked_pages", metric, k)
            paired_counts[str(k)][metric] = {
                "original_rrf_successes": original_count,
                "visual_rerank_successes": visual_count,
                "net_change_questions": visual_count - original_count,
                "paired_outcomes": {
                    outcome: sum(
                        item["scores"][str(k)]["paired_outcome"][metric] == outcome
                        for item in evaluated
                    )
                    for outcome in ("visual_gain", "visual_loss", "both_success", "both_failure")
                },
            }

    complete_3 = paired_counts["3"]["complete_evidence_recall"]["net_change_questions"]
    complete_5 = paired_counts["5"]["complete_evidence_recall"]["net_change_questions"]
    any_3 = paired_counts["3"]["any_evidence_recall"]["net_change_questions"]
    any_5 = paired_counts["5"]["any_evidence_recall"]["net_change_questions"]
    checks = {
        "complete_gain_at_least_four_at_k3_or_k5": max(complete_3, complete_5) >= 4,
        "complete_non_decrease_at_other_k": (
            complete_5 >= 0 if complete_3 >= 4 else complete_3 >= 0 if complete_5 >= 4 else False
        ),
        "any_loss_no_more_than_one_at_k3": any_3 >= -1,
        "any_loss_no_more_than_one_at_k5": any_5 >= -1,
        "all_questions_processed": len(evaluated) == blind_run.get("question_count") == 63,
        "candidate_page_provenance_preserved": all(
            set(item["original_rrf_pages"]) == set(item["visual_reranked_pages"])
            for item in evaluated
        ),
    }
    return {
        "schema_version": 1,
        "experiment_type": "question_conditioned_visual_retrieval_v1",
        "split": "development_tune",
        "question_count": len(evaluated),
        "aggregate": {"original_rrf": original_aggregate, "visual_rerank": visual_aggregate},
        "paired_success_counts": paired_counts,
        "page_span_slices": {
            span: {
                "question_count": len(subset),
                "original_rrf": _aggregate(subset, "original_rrf_pages"),
                "visual_rerank": _aggregate(subset, "visual_reranked_pages"),
            }
            for span in ("single", "multi")
            if (subset := [item for item in evaluated if item["page_span"] == span])
        },
        "keep_drop_gate": {
            "checks": checks,
            "passed": all(checks.values()),
            "decision": "keep_visual_reranker" if all(checks.values()) else "drop_visual_reranker",
        },
        "per_question": evaluated,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blind-rankings", required=True, type=Path)
    parser.add_argument("--rrf-run", required=True, type=Path)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable output: {args.output}")
    blind = json.loads(args.blind_rankings.read_text(encoding="utf-8"))
    rrf = json.loads(args.rrf_run.read_text(encoding="utf-8"))
    result = score_visual_rankings(blind, rrf)
    result["input_sha256"] = {
        "blind_rankings": sha256_file(args.blind_rankings),
        "rrf_run": sha256_file(args.rrf_run),
        "protocol": sha256_file(args.protocol),
    }
    write_json(args.output, result)
    print(json.dumps({
        "output": str(args.output),
        "output_sha256": sha256_file(args.output),
        "question_count": result["question_count"],
        "paired_success_counts": result["paired_success_counts"],
        "keep_drop_gate": result["keep_drop_gate"],
        "paid_api_used": False,
    }, indent=2))


if __name__ == "__main__":
    main()
