"""Deterministic binary evidence-page metrics."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Iterable, Sequence

from .constants import ANSWERABLE_ZERO_EVIDENCE_ID


def _pages(values: Iterable[int], field: str) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{field} must contain positive integer 1-based page IDs")
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


@dataclass(frozen=True)
class PageScore:
    k: int
    gold_count: int
    predicted_count: int
    true_positive: int
    any_evidence_recall: float
    complete_evidence_recall: float
    recall: float
    precision: float
    f1: float
    reciprocal_rank: float
    ndcg: float

    def to_dict(self) -> dict[str, int | float]:
        return asdict(self)


def score_evidence_pages(
    gold_pages: Iterable[int], predicted_pages: Sequence[int], k: int
) -> PageScore:
    """Score one answerable question with at least one gold page.

    Predictions are ranked, duplicate pages are removed at first occurrence, and K is applied
    after de-duplication. Precision uses the requested K as denominator, matching retrieval@K.
    """
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ValueError("k must be a positive integer")
    gold = set(_pages(gold_pages, "gold_pages"))
    if not gold:
        raise ValueError("evidence scoring requires at least one gold page")
    ranked = _pages(predicted_pages, "predicted_pages")[:k]
    hits = [page in gold for page in ranked]
    tp = sum(hits)
    recall = tp / len(gold)
    precision = tp / k
    f1 = 0.0 if recall + precision == 0 else 2 * recall * precision / (recall + precision)
    first = next((index for index, hit in enumerate(hits, start=1) if hit), None)
    dcg = sum((1.0 / math.log2(index + 1)) for index, hit in enumerate(hits, start=1) if hit)
    ideal_hits = min(len(gold), k)
    idcg = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_hits + 1))
    return PageScore(
        k=k,
        gold_count=len(gold),
        predicted_count=len(ranked),
        true_positive=tp,
        any_evidence_recall=float(tp > 0),
        complete_evidence_recall=float(tp == len(gold)),
        recall=recall,
        precision=precision,
        f1=f1,
        reciprocal_rank=0.0 if first is None else 1.0 / first,
        ndcg=dcg / idcg,
    )


def aggregate_page_scores(scores: Sequence[PageScore]) -> dict[str, object]:
    if not scores:
        raise ValueError("at least one score is required")
    mean_fields = (
        "any_evidence_recall",
        "complete_evidence_recall",
        "recall",
        "precision",
        "f1",
        "reciprocal_rank",
        "ndcg",
    )
    macro = {field: sum(getattr(score, field) for score in scores) / len(scores) for field in mean_fields}
    tp = sum(score.true_positive for score in scores)
    gold = sum(score.gold_count for score in scores)
    retrieved_slots = sum(score.k for score in scores)
    micro_recall = tp / gold
    micro_precision = tp / retrieved_slots
    micro_f1 = (
        0.0
        if micro_recall + micro_precision == 0
        else 2 * micro_recall * micro_precision / (micro_recall + micro_precision)
    )
    return {
        "question_count": len(scores),
        "macro": macro,
        "micro": {
            "true_positive": tp,
            "gold_pages": gold,
            "retrieved_slots": retrieved_slots,
            "recall": micro_recall,
            "precision": micro_precision,
            "f1": micro_f1,
        },
    }


def scoring_eligibility(record: dict[str, object]) -> tuple[bool, str | None]:
    """Apply the frozen protocol's evidence-metric denominator rules."""
    answer = record.get("answer")
    if not isinstance(answer, dict) or not answer.get("is_answerable"):
        return False, "unanswerable"
    if record.get("id") == ANSWERABLE_ZERO_EVIDENCE_ID:
        return False, "answerable_zero_evidence_anomaly"
    evidences = record.get("evidences")
    if not isinstance(evidences, list) or not evidences:
        return False, "missing_gold_evidence"
    return True, None
