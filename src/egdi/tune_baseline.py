"""Run the deterministic page-BM25 baseline on development_tune only."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

from .access import load_records
from .bm25 import PageBm25Index
from .corpus import read_page_records_jsonl
from .evaluation import DEFAULT_KS, evaluate_question
from .io import sha256_file, write_json
from .scoring import aggregate_page_scores, score_evidence_pages, scoring_eligibility
from .text import PageRecord


def _read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def load_tune_questions(
    benchmark_path: Path, split_manifest_path: Path
) -> tuple[list[dict[str, Any]], list[str]]:
    """Load guarded dev labels in the frozen development_tune question order."""
    manifest = _read_json_object(split_manifest_path)
    tune = manifest.get("development_tune")
    if not isinstance(tune, dict):
        raise ValueError("split manifest is missing development_tune")
    question_ids = tune.get("question_ids")
    document_ids = tune.get("document_ids")
    if not isinstance(question_ids, list) or not all(
        isinstance(value, str) for value in question_ids
    ):
        raise ValueError("development_tune.question_ids must be a list of strings")
    if not isinstance(document_ids, list) or not all(
        isinstance(value, str) for value in document_ids
    ):
        raise ValueError("development_tune.document_ids must be a list of strings")
    if len(question_ids) != len(set(question_ids)):
        raise ValueError("development_tune contains duplicate question IDs")
    if tune.get("question_count") != len(question_ids):
        raise ValueError("development_tune question_count does not match question_ids")

    dev_records = load_records(benchmark_path, split="dev")
    by_id = {record["id"]: record for record in dev_records}
    missing = [question_id for question_id in question_ids if question_id not in by_id]
    if missing:
        raise ValueError(f"tune question IDs are missing from guarded dev records: {missing}")
    questions = [by_id[question_id] for question_id in question_ids]
    allowed_docs = set(document_ids)
    if any(question["pdf"]["doc_id_str"] not in allowed_docs for question in questions):
        raise ValueError("a tune question points outside the tune document whitelist")
    return questions, document_ids


def load_verified_corpora(
    corpus_manifest_path: Path,
    corpus_dir: Path,
    expected_doc_ids: Sequence[str],
) -> dict[str, list[PageRecord]]:
    """Verify the derived corpus manifest and every JSONL before evaluation."""
    manifest = _read_json_object(corpus_manifest_path)
    if manifest.get("split") != "development_tune":
        raise ValueError("corpus manifest is not development_tune")
    documents = manifest.get("documents")
    if not isinstance(documents, list):
        raise ValueError("corpus manifest is missing documents")
    if len(expected_doc_ids) != len(set(expected_doc_ids)):
        raise ValueError("expected document IDs must be unique")
    by_id: dict[str, dict[str, Any]] = {}
    for document in documents:
        if not isinstance(document, dict) or not isinstance(document.get("doc_id"), str):
            raise ValueError("corpus manifest contains an invalid document")
        if document["doc_id"] in by_id:
            raise ValueError(f"duplicate corpus manifest doc_id: {document['doc_id']}")
        by_id[document["doc_id"]] = document
    if set(by_id) != set(expected_doc_ids):
        raise ValueError("corpus manifest document IDs do not match development_tune")

    corpora: dict[str, list[PageRecord]] = {}
    for doc_id in expected_doc_ids:
        document = by_id[doc_id]
        path = corpus_dir / f"{doc_id}.jsonl"
        if not path.is_file():
            raise FileNotFoundError(f"Page Record corpus is missing: {path}")
        if sha256_file(path) != document.get("output_jsonl_sha256"):
            raise ValueError(f"Page Record checksum mismatch for {doc_id}")
        records = read_page_records_jsonl(path)
        expected_pages = document.get("page_count")
        if len(records) != expected_pages:
            raise ValueError(f"Page Record count mismatch for {doc_id}")
        if any(record.doc_id != doc_id for record in records):
            raise ValueError(f"Page Record doc_id mismatch for {doc_id}")
        if [record.page for record in records] != list(range(1, len(records) + 1)):
            raise ValueError(f"Page Record pages are not sequential for {doc_id}")
        actual_status = Counter(record.extraction_status for record in records)
        expected_status = document.get("status_counts")
        if not isinstance(expected_status, dict) or any(
            actual_status.get(status, 0) != expected_status.get(status, 0)
            for status in ("ok", "low_text", "text_layer_missing")
        ):
            raise ValueError(f"Page Record status counts mismatch for {doc_id}")
        corpora[doc_id] = records
    return corpora


def _gold_text_status(gold_pages: Sequence[int], records: Sequence[PageRecord]) -> str:
    status_by_page = {record.page: record.extraction_status for record in records}
    statuses = [status_by_page[page] for page in gold_pages]
    if "text_layer_missing" in statuses:
        return "text_layer_missing"
    if "low_text" in statuses:
        return "low_text"
    return "ok"


def _evidence_type(question: dict[str, Any]) -> str:
    values = sorted({str(evidence.get("element_type", "unknown")) for evidence in question["evidences"]})
    return values[0] if len(values) == 1 else "mixed"


def _aggregate_results(results: Sequence[dict[str, Any]], ks: Sequence[int]) -> dict[str, Any]:
    if not results:
        return {}
    return {
        str(k): aggregate_page_scores(
            [
                score_evidence_pages(result["gold_pages"], result["retrieved_pages"], k)
                for result in results
            ]
        )
        for k in ks
    }


def evaluate_tune(
    questions: Sequence[dict[str, Any]],
    corpora: dict[str, list[PageRecord]],
    *,
    k1: float = 1.2,
    b: float = 0.75,
    query_token_policy: str = "retain_repetitions",
    ks: Sequence[int] = DEFAULT_KS,
) -> dict[str, Any]:
    """Evaluate eligible tune questions and aggregate predefined diagnostic slices."""
    if not questions:
        raise ValueError("at least one tune question is required")
    indexes: dict[str, PageBm25Index] = {}
    per_question: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []

    for question in questions:
        eligible, reason = scoring_eligibility(question)
        if not eligible:
            exclusions.append({"question_id": question.get("id"), "reason": reason})
            continue
        doc_id = question["pdf"]["doc_id_str"]
        records = corpora.get(doc_id)
        if records is None:
            raise ValueError(f"no Page Record corpus for question document: {doc_id}")
        if doc_id not in indexes:
            indexes[doc_id] = PageBm25Index(
                records,
                k1=k1,
                b=b,
                query_token_policy=query_token_policy,
            )
        result = evaluate_question(indexes[doc_id], question, ks)
        result["doc_id"] = doc_id
        result["slices"] = {
            "page_span": "multi" if len(result["gold_pages"]) > 1 else "single",
            "gold_text_status": _gold_text_status(result["gold_pages"], records),
            "evidence_type": _evidence_type(question),
            "extract_class": str(question.get("extract_class", "unknown")),
        }
        per_question.append(result)

    slice_fields = ("page_span", "gold_text_status", "evidence_type", "extract_class")
    slices: dict[str, dict[str, Any]] = {}
    for field in slice_fields:
        categories = sorted({result["slices"][field] for result in per_question})
        slices[field] = {
            category: _aggregate_results(
                [result for result in per_question if result["slices"][field] == category], ks
            )
            for category in categories
        }

    return {
        "split": "development_tune",
        "corpus_document_count": len(corpora),
        "evaluated_document_count": len(indexes),
        "question_count": len(questions),
        "eligible_question_count": len(per_question),
        "excluded_question_count": len(exclusions),
        "exclusion_reasons": dict(Counter(item["reason"] for item in exclusions)),
        "exclusions": exclusions,
        "aggregate": _aggregate_results(per_question, ks),
        "slices": slices,
        "per_question": per_question,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--split-manifest", required=True, type=Path)
    parser.add_argument("--corpus-manifest", required=True, type=Path)
    parser.add_argument("--corpus-dir", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    config = _read_json_object(args.config)
    k1 = config.get("k1")
    b = config.get("b")
    ks = config.get("top_ks")
    query_token_policy = config.get("query_token_policy", "retain_repetitions")
    if not isinstance(k1, (int, float)) or isinstance(k1, bool):
        raise ValueError("config k1 must be numeric")
    if not isinstance(b, (int, float)) or isinstance(b, bool):
        raise ValueError("config b must be numeric")
    if not isinstance(ks, list):
        raise ValueError("config top_ks must be a list")
    if not isinstance(query_token_policy, str):
        raise ValueError("config query_token_policy must be a string")

    questions, document_ids = load_tune_questions(args.benchmark, args.split_manifest)
    corpora = load_verified_corpora(args.corpus_manifest, args.corpus_dir, document_ids)
    result = evaluate_tune(
        questions,
        corpora,
        k1=float(k1),
        b=float(b),
        query_token_policy=query_token_policy,
        ks=ks,
    )
    result["configuration"] = config
    result["configuration_sha256"] = sha256_file(args.config)
    result["corpus_manifest_sha256"] = sha256_file(args.corpus_manifest)
    write_json(args.output, result)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "output_sha256": sha256_file(args.output),
                "corpus_document_count": result["corpus_document_count"],
                "evaluated_document_count": result["evaluated_document_count"],
                "question_count": result["question_count"],
                "eligible_question_count": result["eligible_question_count"],
                "excluded_question_count": result["excluded_question_count"],
                "aggregate": result["aggregate"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
