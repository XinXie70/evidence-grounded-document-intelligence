"""Freeze label-free validation cases for the generic comparison pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .io import sha256_file, write_json


def select_validation_cases(
    scope: dict[str, Any], retrieval: dict[str, Any], protocol: dict[str, Any]
) -> dict[str, Any]:
    if scope.get("split") != "development_tune":
        raise ValueError("scope must be development_tune")
    if retrieval.get("configuration", {}).get("selection_split") != "development_tune":
        raise ValueError("retrieval results must be development_tune")
    count = protocol.get("validation_case_count")
    excluded_docs = protocol.get("method_development_doc_ids")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError("validation_case_count must be positive")
    if not isinstance(excluded_docs, list) or len(excluded_docs) != len(set(excluded_docs)):
        raise ValueError("method development document exclusions are invalid")

    questions = scope.get("categories", {}).get("difference_wording", {}).get("questions")
    if not isinstance(questions, list):
        raise ValueError("difference question pool is missing")
    retrieval_by_id = {}
    for item in retrieval.get("per_question", []):
        question_id = item.get("question_id")
        pages = item.get("retrieved_pages")
        if isinstance(question_id, str) and isinstance(pages, list):
            retrieval_by_id[question_id] = {
                "doc_id": item.get("doc_id"),
                "question": item.get("question"),
                "candidate_pages": pages[:10],
            }

    selected = []
    seen_docs: set[str] = set()
    for question in sorted(questions, key=lambda item: item["question_id"]):
        question_id = question["question_id"]
        retrieved = retrieval_by_id.get(question_id)
        if retrieved is None or len(retrieved["candidate_pages"]) != 10:
            continue
        doc_id = retrieved["doc_id"]
        if doc_id in excluded_docs or doc_id in seen_docs:
            continue
        if retrieved["question"] != question["question"]:
            raise ValueError(f"question text drift: {question_id}")
        seen_docs.add(doc_id)
        selected.append({
            "case_id": f"validation_{len(selected) + 1:02d}",
            "question_id": question_id,
            "doc_id": doc_id,
            "question": question["question"],
            "candidate_pages": retrieved["candidate_pages"],
            "retrieval_method": "hybrid_rrf_bm25_dense_v0_top10",
            "page_records": f"data/derived/page_records/{doc_id}.jsonl",
            "uses_gold_answer": False,
            "uses_gold_evidence_pages": False,
        })
        if len(selected) == count:
            break
    if len(selected) != count:
        raise ValueError("not enough eligible validation cases")
    return {
        "schema_version": 1,
        "experiment_type": "frozen_generic_comparison_validation_selection",
        "split": "development_tune",
        "case_count": len(selected),
        "cases": selected,
        "selection_policy": (
            "lexicographically_first_difference_questions_from_distinct_documents_"
            "excluding_all_method_development_documents"
        ),
        "leakage_controls": {
            "uses_gold_answer": False,
            "uses_gold_evidence_pages": False,
            "uses_retrieval_scores": False,
            "uses_retrieved_page_order_only": True,
        },
        "paid_api_used": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", required=True, type=Path)
    parser.add_argument("--retrieval", required=True, type=Path)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite frozen selection: {args.output}")
    result = select_validation_cases(
        json.loads(args.scope.read_text(encoding="utf-8")),
        json.loads(args.retrieval.read_text(encoding="utf-8")),
        json.loads(args.protocol.read_text(encoding="utf-8")),
    )
    result["source_sha256"] = {
        "scope": sha256_file(args.scope),
        "retrieval": sha256_file(args.retrieval),
        "protocol": sha256_file(args.protocol),
    }
    write_json(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
