"""Deterministic document-grouped development split generation."""

from __future__ import annotations

import hashlib
import random
from collections import Counter, defaultdict
from typing import Any, Iterable

from .constants import SPLIT_SEED


TEXT_TYPES = {"text", "paragraph_title", "title"}
TABLE_TYPES = {"table"}
CHART_TYPES = {"chart"}
IMAGE_TYPES = {"image", "figure"}


def evidence_modality(record: dict[str, Any]) -> str:
    categories: set[str] = set()
    for evidence in record.get("evidences", []):
        element = str(evidence.get("element_type", "unknown")).lower()
        if element in TABLE_TYPES:
            categories.add("table")
        elif element in CHART_TYPES:
            categories.add("chart")
        elif element in IMAGE_TYPES:
            categories.add("image_figure")
        elif element in TEXT_TYPES:
            categories.add("text")
        else:
            categories.add("other")
    if not categories:
        return "none"
    return next(iter(categories)) if len(categories) == 1 else "mixed"


def record_strata(record: dict[str, Any]) -> tuple[str, ...]:
    pages = {evidence["page"] for evidence in record.get("evidences", [])}
    return (
        f"answerable={bool(record['answer']['is_answerable'])}",
        f"extract_class={record.get('extract_class', 'missing')}",
        f"modality={evidence_modality(record)}",
        f"page_span={'multi' if len(pages) > 1 else 'single_or_none'}",
    )


def _counts(records: Iterable[dict[str, Any]]) -> Counter[str]:
    result: Counter[str] = Counter()
    for record in records:
        result["questions"] += 1
        result.update(record_strata(record))
    return result


def build_split_manifest(records: list[dict[str, Any]]) -> dict[str, Any]:
    dev = [record for record in records if record["split"] == "dev"]
    test_docs = {record["pdf"]["doc_id_str"] for record in records if record["split"] == "test"}
    excluded = [record for record in dev if record["pdf"]["doc_id_str"] in test_docs]
    clean = [record for record in dev if record["pdf"]["doc_id_str"] not in test_docs]
    by_doc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in clean:
        by_doc[record["pdf"]["doc_id_str"]].append(record)

    doc_ids = sorted(by_doc)
    calibration_doc_count = round(len(doc_ids) * 0.30)
    target = _counts(clean)
    target = Counter({key: value * 0.30 for key, value in target.items()})
    doc_counts = {doc_id: _counts(by_doc[doc_id]) for doc_id in doc_ids}
    rng = random.Random(SPLIT_SEED)
    tie_order = doc_ids.copy()
    rng.shuffle(tie_order)
    tie_rank = {doc_id: rank for rank, doc_id in enumerate(tie_order)}

    chosen: list[str] = []
    current: Counter[str] = Counter()
    keys = sorted(target)
    for _ in range(calibration_doc_count):
        def loss(doc_id: str) -> tuple[float, int]:
            candidate = current + doc_counts[doc_id]
            normalized_error = sum(
                ((candidate[key] - target[key]) / max(target[key], 1.0)) ** 2 for key in keys
            )
            return normalized_error, tie_rank[doc_id]

        best = min((doc_id for doc_id in doc_ids if doc_id not in chosen), key=loss)
        chosen.append(best)
        current.update(doc_counts[best])

    calibration_docs = sorted(chosen)
    tune_docs = sorted(set(doc_ids) - set(calibration_docs))

    def partition(documents: list[str]) -> dict[str, Any]:
        subset = [record for doc_id in documents for record in by_doc[doc_id]]
        return {
            "document_ids": documents,
            "question_ids": sorted(record["id"] for record in subset),
            "document_count": len(documents),
            "question_count": len(subset),
            "strata": dict(sorted(_counts(subset).items())),
        }

    manifest = {
        "schema_version": 1,
        "dataset": "DocScope",
        "seed": SPLIT_SEED,
        "grouping_unit": "pdf.doc_id_str",
        "strategy": "greedy 30% calibration selection minimizing normalized squared stratum error",
        "stratification_targets": [
            "answerability",
            "extract_class",
            "evidence_modality",
            "single_or_none_vs_multi_page",
        ],
        "excluded_official_dev_document_ids": sorted(
            {record["pdf"]["doc_id_str"] for record in excluded}
        ),
        "excluded_official_dev_question_ids": sorted(record["id"] for record in excluded),
        "development_tune": partition(tune_docs),
        "development_calibration": partition(calibration_docs),
        "locked_test": {
            "document_ids": sorted(test_docs),
            "document_count": len(test_docs),
            "question_count": sum(record["split"] == "test" for record in records),
            "question_ids_sha256": hashlib.sha256(
                "\n".join(sorted(record["id"] for record in records if record["split"] == "test")).encode()
            ).hexdigest(),
            "question_ids_omitted": True,
        },
    }
    return manifest

