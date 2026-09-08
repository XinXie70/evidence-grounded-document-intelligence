"""Evaluate the frozen R2 retrieval candidate on its tune-only inventory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .corpus import read_page_records_jsonl
from .io import sha256_file, write_json
from .text import PageRecord
from .tune_baseline import evaluate_tune, load_tune_questions


def select_inventory_questions(
    tune_questions: Sequence[dict[str, Any]], inventory: dict[str, Any]
) -> list[dict[str, Any]]:
    """Select the exact ordered R2 question set declared by the inventory."""
    if inventory.get("split") != "development_tune":
        raise ValueError("R2 inventory is not development_tune")
    requested = [
        question["question_id"]
        for document in inventory.get("documents", [])
        for question in document.get("questions", [])
    ]
    if len(requested) != len(set(requested)):
        raise ValueError("R2 inventory contains duplicate question IDs")
    by_id = {question["id"]: question for question in tune_questions}
    missing = [question_id for question_id in requested if question_id not in by_id]
    if missing:
        raise ValueError(f"R2 inventory questions are absent from tune: {missing}")
    selected = [by_id[question_id] for question_id in requested]
    if inventory.get("question_count") != len(selected):
        raise ValueError("R2 inventory question_count does not match questions")
    return selected


def load_registered_r2_corpora(
    registry: dict[str, Any], expected_doc_ids: Sequence[str], *, root: Path
) -> dict[str, list[PageRecord]]:
    """Load OCR corpora after checking identity, continuity, count, and checksum."""
    documents = registry.get("documents")
    if not isinstance(documents, list):
        raise ValueError("OCR registry must contain documents")
    by_id: dict[str, dict[str, Any]] = {}
    for document in documents:
        doc_id = document.get("doc_id") if isinstance(document, dict) else None
        if not isinstance(doc_id, str) or not doc_id:
            raise ValueError("OCR registry contains an invalid document")
        if doc_id in by_id:
            raise ValueError(f"duplicate OCR registry doc_id: {doc_id}")
        by_id[doc_id] = document
    if set(by_id) != set(expected_doc_ids):
        raise ValueError("OCR registry document IDs do not match R2 inventory")

    corpora: dict[str, list[PageRecord]] = {}
    for doc_id in expected_doc_ids:
        metadata = by_id[doc_id]
        path = root / metadata["corpus_path"]
        if not path.is_file():
            raise FileNotFoundError(f"registered OCR corpus is missing: {path}")
        if sha256_file(path) != metadata.get("corpus_sha256"):
            raise ValueError(f"registered OCR corpus checksum mismatch: {doc_id}")
        records = read_page_records_jsonl(path)
        if len(records) != metadata.get("page_count"):
            raise ValueError(f"registered OCR page count mismatch: {doc_id}")
        if any(record.doc_id != doc_id for record in records):
            raise ValueError(f"registered OCR doc_id mismatch: {doc_id}")
        if [record.page for record in records] != list(range(1, len(records) + 1)):
            raise ValueError(f"registered OCR pages are not sequential: {doc_id}")
        corpora[doc_id] = records
    return corpora


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--split-manifest", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--ocr-registry", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    inventory = _read_json(args.inventory)
    registry = _read_json(args.ocr_registry)
    config = _read_json(args.config)
    tune_questions, _ = load_tune_questions(args.benchmark, args.split_manifest)
    questions = select_inventory_questions(tune_questions, inventory)
    doc_ids = [document["doc_id"] for document in inventory["documents"]]
    corpora = load_registered_r2_corpora(registry, doc_ids, root=Path.cwd())
    retrieval = config.get("retrieval")
    if not isinstance(retrieval, dict):
        raise ValueError("R2 candidate config is missing retrieval")
    top_k = retrieval.get("top_k")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
        raise ValueError("R2 candidate top_k must be a positive integer")
    ks = sorted({1, 3, 5, top_k})
    result = evaluate_tune(
        questions,
        corpora,
        k1=float(retrieval["k1"]),
        b=float(retrieval["b"]),
        query_token_policy=retrieval["query_token_policy"],
        ks=ks,
    )
    result["route"] = config["route"]
    result["candidate_status"] = config["status"]
    result["uses_gold_labels_only_after_retrieval"] = True
    result["inputs"] = {
        "inventory_sha256": sha256_file(args.inventory),
        "ocr_registry_sha256": sha256_file(args.ocr_registry),
        "config_sha256": sha256_file(args.config),
        "corpus_sha256_by_doc": {
            document["doc_id"]: document["corpus_sha256"]
            for document in registry["documents"]
        },
    }
    write_json(args.output, result)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "output_sha256": sha256_file(args.output),
                "document_count": result["evaluated_document_count"],
                "eligible_question_count": result["eligible_question_count"],
                "excluded_question_count": result["excluded_question_count"],
                "aggregate": result["aggregate"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
