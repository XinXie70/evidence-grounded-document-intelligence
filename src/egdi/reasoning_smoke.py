"""Validate a frozen smoke selection and generate paired reasoning inputs locally."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .access import load_records
from .bm25 import PageBm25Index
from .corpus import read_page_records_jsonl
from .io import sha256_file, write_json
from .reasoning_inputs import (
    ReasoningInput,
    build_reasoning_pair,
    build_reasoning_triplet,
)
from .text import PageRecord


def _read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def build_smoke_cases(
    selection: dict[str, Any],
    questions: dict[str, dict[str, Any]],
    page_records_by_doc: dict[str, Sequence[PageRecord]],
    *,
    tune_question_ids: set[str],
    k1: float,
    b: float,
) -> list[tuple[str, ReasoningInput, ReasoningInput]]:
    """Recompute Top-K and build all selected real/Oracle pairs without gold-answer leakage."""
    if selection.get("status") != "frozen_for_smoke_v1":
        raise ValueError("selection must be frozen_for_smoke_v1")
    if selection.get("split") != "development_tune":
        raise ValueError("selection must use development_tune")
    top_k = selection.get("top_k")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
        raise ValueError("selection.top_k must be a positive integer")
    selected = selection.get("questions")
    if not isinstance(selected, list) or len(selected) != selection.get("question_count"):
        raise ValueError("selection question count does not match questions")

    case_ids = [item.get("case_id") for item in selected if isinstance(item, dict)]
    question_ids = [item.get("question_id") for item in selected if isinstance(item, dict)]
    doc_ids = [item.get("doc_id") for item in selected if isinstance(item, dict)]
    if len(case_ids) != len(selected) or len(set(case_ids)) != len(case_ids):
        raise ValueError("case IDs must be present and unique")
    if len(question_ids) != len(selected) or len(set(question_ids)) != len(question_ids):
        raise ValueError("question IDs must be present and unique")
    if len(doc_ids) != len(selected) or len(set(doc_ids)) != len(doc_ids):
        raise ValueError("smoke questions must use distinct documents")

    built: list[tuple[str, ReasoningInput, ReasoningInput]] = []
    for item in selected:
        case_id = item["case_id"]
        question_id = item["question_id"]
        doc_id = item["doc_id"]
        if question_id not in tune_question_ids:
            raise ValueError(f"selected question is not in development_tune: {question_id}")
        if question_id not in questions:
            raise ValueError(f"selected question is absent from guarded dev data: {question_id}")
        question = questions[question_id]
        if question.get("question") != item.get("question"):
            raise ValueError(f"question text mismatch: {question_id}")
        pdf = question.get("pdf")
        if not isinstance(pdf, dict) or pdf.get("doc_id_str") != doc_id:
            raise ValueError(f"document mismatch: {question_id}")
        answer = question.get("answer")
        answerable = answer.get("is_answerable") if isinstance(answer, dict) else None
        expected_answerable = item.get("answerability") == "answerable"
        if not isinstance(answerable, bool) or answerable != expected_answerable:
            raise ValueError(f"answerability mismatch: {question_id}")

        if doc_id not in page_records_by_doc:
            raise ValueError(f"Page Records are absent for document: {doc_id}")
        records = page_records_by_doc[doc_id]
        ranking = PageBm25Index(records, k1=k1, b=b).search(question["question"], top_k)
        retrieved_pages = [result.page for result in ranking]
        if retrieved_pages != item.get("real_retrieval_top3_pages"):
            raise ValueError(f"recomputed retrieval mismatch: {question_id}")

        if answerable:
            evidences = question.get("evidences")
            if not isinstance(evidences, list):
                raise ValueError(f"evidences are invalid: {question_id}")
            gold_pages = sorted({evidence.get("page") for evidence in evidences})
            if gold_pages != item.get("gold_pages"):
                raise ValueError(f"gold-page mismatch: {question_id}")
        elif item.get("gold_pages") != []:
            raise ValueError(f"unanswerable Oracle context must be empty: {question_id}")

        real, oracle = build_reasoning_pair(
            question,
            records,
            retrieved_pages,
            top_k=top_k,
        )
        built.append((case_id, real, oracle))
    return built


def build_smoke_triplet_cases(
    selection: dict[str, Any],
    questions: dict[str, dict[str, Any]],
    page_records_by_doc: dict[str, Sequence[PageRecord]],
    *,
    tune_question_ids: set[str],
    k1: float,
    b: float,
) -> list[tuple[str, ReasoningInput, ReasoningInput, ReasoningInput]]:
    """Build prompt-matched C0/C1/C2 inputs after all frozen smoke checks pass."""
    pairs = build_smoke_cases(
        selection,
        questions,
        page_records_by_doc,
        tune_question_ids=tune_question_ids,
        k1=k1,
        b=b,
    )
    triplets: list[tuple[str, ReasoningInput, ReasoningInput, ReasoningInput]] = []
    for case_id, old_real, _old_oracle in pairs:
        closed, real, oracle = build_reasoning_triplet(
            questions[old_real.question_id],
            page_records_by_doc[old_real.doc_id],
            [page.page for page in old_real.evidence],
            top_k=selection["top_k"],
        )
        triplets.append((case_id, closed, real, oracle))
    return triplets


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--split-manifest", required=True, type=Path)
    parser.add_argument("--retrieval-results", required=True, type=Path)
    parser.add_argument("--page-record-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--include-closed-book", action="store_true")
    args = parser.parse_args()

    selection = _read_json_object(args.selection)
    split_manifest = _read_json_object(args.split_manifest)
    retrieval = _read_json_object(args.retrieval_results)
    if retrieval.get("split") != "development_tune":
        raise ValueError("retrieval result is not development_tune")
    if retrieval.get("configuration_sha256") != selection.get(
        "retrieval_configuration_sha256"
    ):
        raise ValueError("retrieval configuration checksum mismatch")
    retrieval_config = retrieval.get("configuration")
    if not isinstance(retrieval_config, dict):
        raise ValueError("retrieval configuration is missing")

    questions = {record["id"]: record for record in load_records(args.benchmark, split="dev")}
    tune_section = split_manifest.get("development_tune")
    if not isinstance(tune_section, dict) or not isinstance(
        tune_section.get("question_ids"), list
    ):
        raise ValueError("development_tune question IDs are missing")
    tune_question_ids = set(tune_section["question_ids"])

    selected_doc_ids = [item["doc_id"] for item in selection["questions"]]
    page_records_by_doc = {
        doc_id: read_page_records_jsonl(args.page_record_dir / f"{doc_id}.jsonl")
        for doc_id in selected_doc_ids
    }
    if args.include_closed_book:
        triplets = build_smoke_triplet_cases(
            selection,
            questions,
            page_records_by_doc,
            tune_question_ids=tune_question_ids,
            k1=retrieval_config["k1"],
            b=retrieval_config["b"],
        )
        case_views = [
            (case_id, closed, real, oracle)
            for case_id, closed, real, oracle in triplets
        ]
    else:
        pairs = build_smoke_cases(
            selection,
            questions,
            page_records_by_doc,
            tune_question_ids=tune_question_ids,
            k1=retrieval_config["k1"],
            b=retrieval_config["b"],
        )
        case_views = [
            (case_id, None, real, oracle) for case_id, real, oracle in pairs
        ]

    conditions = (
        ["closed_book", "real_retrieval", "oracle_page"]
        if args.include_closed_book
        else ["real_retrieval", "oracle_page"]
    )

    preview = {
        "mode": "execute" if args.execute else "dry_run",
        "paid_request_sent": False,
        "selection_sha256": sha256_file(args.selection),
        "case_count": len(case_views),
        "conditions": conditions,
        "input_file_count": len(case_views) * len(conditions),
        "top_k": selection["top_k"],
        "output_dir": str(args.output_dir),
        "cases": [
            {
                "case_id": case_id,
                "question_id": real.question_id,
                "real_retrieval_pages": [page.page for page in real.evidence],
                "oracle_pages": [page.page for page in oracle.evidence],
            }
            for case_id, _closed, real, oracle in case_views
        ],
    }
    if not args.execute:
        print(json.dumps(preview, indent=2, ensure_ascii=False))
        return

    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty output dir: {args.output_dir}")

    manifest_cases: list[dict[str, Any]] = []
    for case_id, closed, real, oracle in case_views:
        case_dir = args.output_dir / case_id
        closed_path = case_dir / "closed_book.json"
        real_path = case_dir / "real_retrieval.json"
        oracle_path = case_dir / "oracle_page.json"
        if closed is not None:
            write_json(closed_path, closed.to_experiment_record())
        write_json(real_path, real.to_experiment_record())
        write_json(oracle_path, oracle.to_experiment_record())
        manifest_case = {
                "case_id": case_id,
                "question_id": real.question_id,
                "real_retrieval": {
                    "path": str(real_path),
                    "sha256": sha256_file(real_path),
                    "pages": [page.page for page in real.evidence],
                    "evidence_characters": sum(len(page.text) for page in real.evidence),
                },
                "oracle_page": {
                    "path": str(oracle_path),
                    "sha256": sha256_file(oracle_path),
                    "pages": [page.page for page in oracle.evidence],
                    "evidence_characters": sum(len(page.text) for page in oracle.evidence),
                },
            }
        if closed is not None:
            manifest_case["closed_book"] = {
                "path": str(closed_path),
                "sha256": sha256_file(closed_path),
                "pages": [],
                "evidence_characters": 0,
            }
        manifest_cases.append(manifest_case)
    output_manifest = {
        "schema_version": 1,
        "paid_request_sent": False,
        "selection_sha256": sha256_file(args.selection),
        "retrieval_results_sha256": sha256_file(args.retrieval_results),
        "split_manifest_sha256": sha256_file(args.split_manifest),
        "case_count": len(case_views),
        "conditions": conditions,
        "input_file_count": len(case_views) * len(conditions),
        "cases": manifest_cases,
    }
    manifest_path = args.output_dir / "manifest.json"
    write_json(manifest_path, output_manifest)
    preview["manifest"] = str(manifest_path)
    preview["manifest_sha256"] = sha256_file(manifest_path)
    print(json.dumps(preview, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
