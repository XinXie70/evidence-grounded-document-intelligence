"""Create an immutable label-free question selection for an unlocked development split."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from .access import require_evaluation_split_access
from .io import sha256_file, write_json


ALLOWED_SPLITS = {"development_tune", "development_calibration", "locked_test"}
OUTPUT_FIELDS = {"pilot_id", "question_id", "doc_id", "question"}


def build_label_free_selection(
    benchmark: Sequence[dict[str, Any]],
    split_manifest: dict[str, Any],
    *,
    split_name: str,
) -> list[dict[str, str]]:
    if split_name not in ALLOWED_SPLITS:
        raise ValueError("unknown selection split")
    require_evaluation_split_access(split_name)
    section = split_manifest.get(split_name)
    if not isinstance(section, dict):
        raise ValueError(f"split manifest is missing {split_name}")
    document_ids = section.get("document_ids")
    if not isinstance(document_ids, list) or not all(isinstance(x, str) for x in document_ids):
        raise ValueError("split document_ids must be a list of strings")
    allowed_documents = set(document_ids)
    by_id: dict[str, dict[str, Any]] = {}
    for row in benchmark:
        question_id = row.get("id")
        if isinstance(question_id, str):
            if question_id in by_id:
                raise ValueError(f"benchmark contains duplicate question ID: {question_id}")
            by_id[question_id] = row
    if split_name == "locked_test":
        question_ids = sorted(
            question_id
            for question_id, row in by_id.items()
            if row.get("split") == "test"
            and isinstance(row.get("pdf"), dict)
            and row["pdf"].get("doc_id_str") in allowed_documents
        )
        observed_hash = hashlib.sha256("\n".join(question_ids).encode()).hexdigest()
        if section.get("question_ids_omitted") is not True:
            raise ValueError("locked-test question IDs must be omitted from the split manifest")
        if observed_hash != section.get("question_ids_sha256"):
            raise ValueError("locked-test question identity hash mismatch")
    else:
        question_ids = section.get("question_ids")
        if not isinstance(question_ids, list) or not all(isinstance(x, str) for x in question_ids):
            raise ValueError("split question_ids must be a list of strings")
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("split question_ids must be unique")

    output = []
    for index, question_id in enumerate(question_ids, start=1):
        row = by_id.get(question_id)
        if row is None:
            raise ValueError(f"benchmark is missing split question: {question_id}")
        pdf = row.get("pdf")
        doc_id = pdf.get("doc_id_str") if isinstance(pdf, dict) else None
        question = row.get("question")
        if doc_id not in allowed_documents:
            raise ValueError(f"question document is outside {split_name}: {question_id}")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"question text is invalid: {question_id}")
        prefix = {
            "development_tune": "tune",
            "development_calibration": "calibration",
            "locked_test": "locked_test",
        }[split_name]
        projected = {
            "pilot_id": f"{prefix}_{index:03d}",
            "question_id": question_id,
            "doc_id": doc_id,
            "question": question,
        }
        if set(projected) != OUTPUT_FIELDS:
            raise AssertionError("label-free projection drift")
        output.append(projected)
    if section.get("question_count") != len(output):
        raise ValueError("split question_count does not match question_ids")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--split-manifest", required=True, type=Path)
    parser.add_argument("--split", choices=sorted(ALLOWED_SPLITS), required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    require_evaluation_split_access(args.split)
    benchmark = json.loads(args.benchmark.read_text(encoding="utf-8"))
    split_manifest = json.loads(args.split_manifest.read_text(encoding="utf-8"))
    if not isinstance(benchmark, list) or not isinstance(split_manifest, dict):
        raise ValueError("benchmark must be a list and split manifest must be an object")
    questions = build_label_free_selection(
        benchmark, split_manifest, split_name=args.split
    )
    artifact = {
        "schema_version": 1,
        "status": "label_free_selection_frozen_before_prediction",
        "split": args.split,
        "contains_gold_or_answer_labels": False,
        "question_count": len(questions),
        "document_count": len({item["doc_id"] for item in questions}),
        "source": {
            "benchmark_sha256": sha256_file(args.benchmark),
            "split_manifest_sha256": sha256_file(args.split_manifest),
            "projected_fields": sorted(OUTPUT_FIELDS),
        },
        "questions": questions,
    }
    write_json(args.output, artifact)
    print(json.dumps({
        "output": str(args.output),
        "output_sha256": sha256_file(args.output),
        "split": args.split,
        "question_count": len(questions),
        "document_count": artifact["document_count"],
        "contains_gold_or_answer_labels": False,
    }, indent=2))


if __name__ == "__main__":
    main()
