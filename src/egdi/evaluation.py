"""Evaluate page-level BM25 retrieval against gold evidence pages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Protocol, Sequence

from .access import load_records
from .bm25 import PageBm25Index
from .corpus import read_page_records_jsonl
from .scoring import aggregate_page_scores, score_evidence_pages, scoring_eligibility
from .text import PageRecord


DEFAULT_KS = (1, 3, 5, 10)


class RankedPage(Protocol):
    page: int


class PageRetrievalIndex(Protocol):
    records: Sequence[PageRecord]

    def search(self, query: str, top_k: int) -> Sequence[RankedPage]: ...


def evaluate_question(
    index: PageRetrievalIndex,
    question_record: dict[str, Any],
    ks: Sequence[int] = DEFAULT_KS,
) -> dict[str, Any]:
    """Retrieve once, then score one eligible question at every requested K."""
    eligible, reason = scoring_eligibility(question_record)
    if not eligible:
        raise ValueError(f"question is not eligible for evidence scoring: {reason}")
    if not ks or any(isinstance(k, bool) or not isinstance(k, int) or k < 1 for k in ks):
        raise ValueError("ks must contain positive integers")

    question = question_record.get("question")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a non-empty string")
    pdf = question_record.get("pdf")
    if not isinstance(pdf, dict) or not isinstance(pdf.get("doc_id_str"), str):
        raise ValueError("question must contain pdf.doc_id_str")
    doc_id = pdf["doc_id_str"]
    if any(record.doc_id != doc_id for record in index.records):
        raise ValueError("retrieval index contains pages from a different document")

    gold_pages = sorted({evidence["page"] for evidence in question_record["evidences"]})
    ranking = index.search(question, top_k=max(ks))
    predicted_pages = [result.page for result in ranking]
    scores = {
        str(k): score_evidence_pages(gold_pages, predicted_pages, k).to_dict()
        for k in ks
    }
    return {
        "question_id": question_record.get("id"),
        "question": question,
        "gold_pages": gold_pages,
        "retrieved_pages": predicted_pages,
        "scores": scores,
    }


def evaluate_document(
    index: PageRetrievalIndex,
    question_records: Sequence[dict[str, Any]],
    ks: Sequence[int] = DEFAULT_KS,
) -> dict[str, Any]:
    """Evaluate eligible questions and report protocol exclusions separately."""
    if not question_records:
        raise ValueError("at least one question record is required")
    eligible_records: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    for record in question_records:
        eligible, reason = scoring_eligibility(record)
        if eligible:
            eligible_records.append(record)
        else:
            exclusions.append({"question_id": record.get("id"), "reason": reason})

    per_question = [evaluate_question(index, record, ks) for record in eligible_records]
    aggregate = {
        str(k): aggregate_page_scores(
            [
                score_evidence_pages(
                    result["gold_pages"], result["retrieved_pages"], k
                )
                for result in per_question
            ]
        )
        for k in ks
    } if per_question else {}
    return {
        "eligible_question_count": len(per_question),
        "excluded_question_count": len(exclusions),
        "exclusions": exclusions,
        "per_question": per_question,
        "aggregate": aggregate,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--doc-id", required=True)
    parser.add_argument("--ks", nargs="+", type=int, default=list(DEFAULT_KS))
    args = parser.parse_args()

    dev_records = load_records(args.benchmark, split="dev")
    questions = [
        record for record in dev_records if record["pdf"]["doc_id_str"] == args.doc_id
    ]
    records = read_page_records_jsonl(args.corpus)
    index = PageBm25Index(records)
    result = evaluate_document(index, questions, args.ks)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
