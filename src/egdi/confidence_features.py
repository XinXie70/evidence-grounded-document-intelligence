"""Extract answer-free inference-time BM25 confidence features on tune queries."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any, Sequence

from .bm25 import PageBm25Index
from .io import sha256_file, write_json
from .text import PageRecord, tokenize_for_bm25
from .tune_baseline import (
    _read_json_object,
    load_tune_questions,
    load_verified_corpora,
)


FORBIDDEN_FEATURE_KEYS = {
    "answer",
    "answer_text",
    "is_answerable",
    "evidences",
    "facts",
    "gold_pages",
    "extract_class",
}


def extract_query_features(
    question_id: str,
    doc_id: str,
    query: str,
    records: Sequence[PageRecord],
    *,
    k1: float = 1.2,
    b: float = 0.75,
) -> dict[str, Any]:
    """Compute only signals available before gold labels are consulted."""
    if not isinstance(question_id, str) or not question_id:
        raise ValueError("question_id must be a non-empty string")
    if not isinstance(doc_id, str) or not doc_id:
        raise ValueError("doc_id must be a non-empty string")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if len(records) < 3:
        raise ValueError("at least three Page Records are required for Top-3 features")
    if any(record.doc_id != doc_id for record in records):
        raise ValueError("all Page Records must match doc_id")

    tokens = tokenize_for_bm25(query)
    if not tokens:
        raise ValueError("query must contain at least one BM25 token")
    ranking = PageBm25Index(records, k1=k1, b=b).search(query, len(records))
    if len(ranking) != len(records):
        raise ValueError("BM25 ranking did not cover every page")
    top3 = ranking[:3]
    top1, top2, top3_result = top3
    status_counts = Counter(result.extraction_status for result in top3)

    return {
        "question_id": question_id,
        "doc_id": doc_id,
        "document_page_count": len(records),
        "query_token_count": len(tokens),
        "query_unique_token_count": len(set(tokens)),
        "bm25_top1_score": top1.score,
        "bm25_top2_score": top2.score,
        "bm25_top3_score": top3_result.score,
        "bm25_top1_top2_margin": top1.score - top2.score,
        "bm25_top1_top3_margin": top1.score - top3_result.score,
        "bm25_positive_page_count": sum(result.score > 0 for result in ranking),
        "top3_pages": [result.page for result in top3],
        "top3_extraction_status_counts": {
            "ok": status_counts.get("ok", 0),
            "low_text": status_counts.get("low_text", 0),
            "text_layer_missing": status_counts.get("text_layer_missing", 0),
        },
    }


def build_tune_feature_artifact(
    questions: Sequence[dict[str, Any]],
    corpora: dict[str, list[PageRecord]],
    *,
    k1: float,
    b: float,
) -> dict[str, Any]:
    """Project guarded tune questions to answer-free runtime feature records."""
    features: list[dict[str, Any]] = []
    for question in questions:
        question_id = question.get("id")
        query = question.get("question")
        pdf = question.get("pdf")
        if not isinstance(pdf, dict) or not isinstance(pdf.get("doc_id_str"), str):
            raise ValueError("question pdf.doc_id_str must be a string")
        doc_id = pdf["doc_id_str"]
        records = corpora.get(doc_id)
        if records is None:
            raise ValueError(f"no Page Record corpus for question document: {doc_id}")
        features.append(
            extract_query_features(
                question_id,
                doc_id,
                query,
                records,
                k1=k1,
                b=b,
            )
        )
    return {
        "schema_version": 1,
        "split": "development_tune",
        "question_count": len(features),
        "contains_gold_or_answer_labels": False,
        "records": features,
    }


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            key in FORBIDDEN_FEATURE_KEYS or _contains_forbidden_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--split-manifest", required=True, type=Path)
    parser.add_argument("--corpus-manifest", required=True, type=Path)
    parser.add_argument("--corpus-dir", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable output: {args.output}")

    config = _read_json_object(args.config)
    k1 = config.get("k1")
    b = config.get("b")
    if isinstance(k1, bool) or not isinstance(k1, (int, float)):
        raise ValueError("config k1 must be numeric")
    if isinstance(b, bool) or not isinstance(b, (int, float)):
        raise ValueError("config b must be numeric")
    questions, document_ids = load_tune_questions(args.benchmark, args.split_manifest)
    corpora = load_verified_corpora(
        args.corpus_manifest, args.corpus_dir, document_ids
    )
    artifact = build_tune_feature_artifact(
        questions, corpora, k1=float(k1), b=float(b)
    )
    if _contains_forbidden_key(artifact):
        raise ValueError("feature artifact contains a forbidden gold or answer key")
    artifact["configuration_sha256"] = sha256_file(args.config)
    artifact["split_manifest_sha256"] = sha256_file(args.split_manifest)
    artifact["corpus_manifest_sha256"] = sha256_file(args.corpus_manifest)
    write_json(args.output, artifact)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "output_sha256": sha256_file(args.output),
                "split": artifact["split"],
                "question_count": artifact["question_count"],
                "contains_gold_or_answer_labels": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
