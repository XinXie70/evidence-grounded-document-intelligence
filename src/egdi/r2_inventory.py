"""Inventory the development-tune scope for the zero-native-text R2 route."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .io import sha256_file, write_json


def _index_unique(records: Sequence[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for record in records:
        value = record.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"record must contain a non-empty {key}")
        if value in indexed:
            raise ValueError(f"duplicate {key}: {value}")
        indexed[value] = record
    return indexed


def build_r2_inventory(
    benchmark: Sequence[dict[str, Any]],
    split_manifest: dict[str, Any],
    page_manifest: dict[str, Any],
    ocr_registry: dict[str, Any],
) -> dict[str, Any]:
    """Select zero-native-text tune documents without reading answer labels."""
    tune = split_manifest.get("development_tune")
    if not isinstance(tune, dict):
        raise ValueError("split manifest must contain development_tune")
    tune_doc_ids = tune.get("document_ids")
    tune_question_ids = tune.get("question_ids")
    if not isinstance(tune_doc_ids, list) or len(tune_doc_ids) != len(set(tune_doc_ids)):
        raise ValueError("development_tune document_ids must be a unique list")
    if not isinstance(tune_question_ids, list) or len(tune_question_ids) != len(
        set(tune_question_ids)
    ):
        raise ValueError("development_tune question_ids must be a unique list")

    pages = page_manifest.get("documents")
    registry = ocr_registry.get("documents")
    if not isinstance(pages, list) or not isinstance(registry, list):
        raise ValueError("page manifest and OCR registry must contain document lists")
    page_by_doc = _index_unique(pages, "doc_id")
    ocr_by_doc = _index_unique(registry, "doc_id")

    questions_by_doc: dict[str, list[dict[str, str]]] = {}
    allowed_questions = set(tune_question_ids)
    observed_question_ids: set[str] = set()
    for record in benchmark:
        question_id = record.get("id")
        pdf = record.get("pdf")
        question = record.get("question")
        if question_id not in allowed_questions:
            continue
        if not isinstance(pdf, dict) or not isinstance(pdf.get("doc_id_str"), str):
            raise ValueError("tune benchmark record is missing pdf.doc_id_str")
        if not isinstance(question, str) or not question.strip():
            raise ValueError("tune benchmark record is missing question text")
        doc_id = pdf["doc_id_str"]
        if doc_id not in tune_doc_ids:
            raise ValueError("tune question points outside tune documents")
        questions_by_doc.setdefault(doc_id, []).append(
            {"question_id": question_id, "question": question}
        )
        observed_question_ids.add(question_id)
    if observed_question_ids != allowed_questions:
        raise ValueError("benchmark and development_tune question IDs do not match")

    documents: list[dict[str, Any]] = []
    for doc_id in sorted(tune_doc_ids):
        metadata = page_by_doc.get(doc_id)
        if metadata is None:
            raise ValueError(f"page manifest is missing tune document: {doc_id}")
        page_count = metadata.get("page_count")
        statuses = metadata.get("status_counts")
        if not isinstance(page_count, int) or page_count < 1 or not isinstance(statuses, dict):
            raise ValueError("page manifest contains invalid page metadata")
        nonempty_pages = statuses.get("ok", 0) + statuses.get("low_text", 0)
        missing_pages = statuses.get("text_layer_missing", 0)
        if nonempty_pages != 0:
            continue
        if missing_pages != page_count:
            raise ValueError("zero-text document status counts do not match page count")

        ocr = ocr_by_doc.get(doc_id)
        if ocr is None:
            ocr_status = "missing"
            ocr_details = None
        else:
            if ocr.get("page_count") != page_count:
                raise ValueError("OCR registry page count does not match native corpus")
            ocr_status = "available"
            ocr_details = {
                key: ocr[key]
                for key in (
                    "corpus_path",
                    "corpus_sha256",
                    "layout_text_dir",
                    "verification_artifact",
                )
            }
        doc_questions = sorted(
            questions_by_doc.get(doc_id, []), key=lambda item: item["question_id"]
        )
        documents.append(
            {
                "doc_id": doc_id,
                "page_count": page_count,
                "question_count": len(doc_questions),
                "questions": doc_questions,
                "ocr_status": ocr_status,
                "ocr": ocr_details,
            }
        )

    return {
        "schema_version": 1,
        "split": "development_tune",
        "route": "r2_scanned_document",
        "trigger": "document_has_zero_native_text_pages",
        "document_count": len(documents),
        "question_count": sum(item["question_count"] for item in documents),
        "page_count": sum(item["page_count"] for item in documents),
        "ocr_available_document_count": sum(
            item["ocr_status"] == "available" for item in documents
        ),
        "ocr_missing_document_count": sum(
            item["ocr_status"] == "missing" for item in documents
        ),
        "documents": documents,
        "uses_gold_or_answer_labels": False,
    }


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_registered_ocr_artifacts(
    inventory: dict[str, Any], *, root: Path
) -> None:
    """Fail if an OCR corpus advertised as available is absent on disk."""
    for document in inventory["documents"]:
        if document["ocr_status"] != "available":
            continue
        ocr = document["ocr"]
        for key in ("corpus_path", "verification_artifact"):
            path = root / ocr[key]
            if not path.is_file():
                raise FileNotFoundError(f"registered OCR {key} does not exist: {path}")
        corpus_path = root / ocr["corpus_path"]
        if sha256_file(corpus_path) != ocr["corpus_sha256"]:
            raise ValueError(
                f"registered OCR corpus checksum mismatch: {document['doc_id']}"
            )
        text_dir = root / ocr["layout_text_dir"]
        if not text_dir.is_dir():
            raise FileNotFoundError(
                f"registered OCR layout_text_dir does not exist: {text_dir}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--split-manifest", required=True, type=Path)
    parser.add_argument("--page-manifest", required=True, type=Path)
    parser.add_argument("--ocr-registry", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    inventory = build_r2_inventory(
        _read_json(args.benchmark),
        _read_json(args.split_manifest),
        _read_json(args.page_manifest),
        _read_json(args.ocr_registry),
    )
    verify_registered_ocr_artifacts(inventory, root=Path.cwd())
    inventory["registered_ocr_artifacts_verified"] = True
    inventory["inputs"] = {
        "benchmark_sha256": sha256_file(args.benchmark),
        "split_manifest_sha256": sha256_file(args.split_manifest),
        "page_manifest_sha256": sha256_file(args.page_manifest),
        "ocr_registry_sha256": sha256_file(args.ocr_registry),
    }
    write_json(args.output, inventory)
    print(json.dumps(inventory, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
