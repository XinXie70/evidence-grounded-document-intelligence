"""Build audited C0/C1/C2 inputs for a frozen Reliability pilot selection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .access import load_records
from .bm25 import PageBm25Index
from .corpus import read_page_records_jsonl
from .io import sha256_file, write_json
from .reasoning_inputs import ReasoningInput, build_reasoning_triplet
from .text import PageRecord


def build_pilot_triplets(
    selection: dict[str, Any],
    questions: dict[str, dict[str, Any]],
    page_records_by_doc: dict[str, Sequence[PageRecord]],
    *,
    tune_question_ids: set[str],
    k1: float,
    b: float,
) -> list[tuple[str, ReasoningInput, ReasoningInput, ReasoningInput]]:
    """Validate the frozen selection and build condition-matched triplets."""
    if selection.get("status") != "frozen_for_reliability_pilot_v0":
        raise ValueError("selection must be frozen_for_reliability_pilot_v0")
    if selection.get("split") != "development_tune":
        raise ValueError("selection must use development_tune")
    selected = selection.get("questions")
    if not isinstance(selected, list) or len(selected) != selection.get("question_count"):
        raise ValueError("selection question count does not match questions")

    pilot_ids = [item.get("pilot_id") for item in selected if isinstance(item, dict)]
    question_ids = [item.get("question_id") for item in selected if isinstance(item, dict)]
    doc_ids = [item.get("doc_id") for item in selected if isinstance(item, dict)]
    for values, label in (
        (pilot_ids, "pilot IDs"),
        (question_ids, "question IDs"),
        (doc_ids, "document IDs"),
    ):
        if len(values) != len(selected) or len(set(values)) != len(values):
            raise ValueError(f"{label} must be present and unique")

    built = []
    for item in selected:
        pilot_id = item["pilot_id"]
        question_id = item["question_id"]
        doc_id = item["doc_id"]
        if question_id not in tune_question_ids:
            raise ValueError(f"selected question is not in development_tune: {question_id}")
        question = questions.get(question_id)
        if question is None:
            raise ValueError(f"selected question is absent from guarded dev data: {question_id}")
        if question.get("question") != item.get("question"):
            raise ValueError(f"question text mismatch: {question_id}")
        pdf = question.get("pdf")
        if not isinstance(pdf, dict) or pdf.get("doc_id_str") != doc_id:
            raise ValueError(f"document mismatch: {question_id}")
        answer = question.get("answer")
        is_answerable = answer.get("is_answerable") if isinstance(answer, dict) else None
        if not isinstance(is_answerable, bool):
            raise ValueError(f"answerability metadata is invalid: {question_id}")
        if is_answerable != (item.get("kind") == "answerable"):
            raise ValueError(f"answerability mismatch: {question_id}")

        records = page_records_by_doc.get(doc_id)
        if records is None:
            raise ValueError(f"Page Records are absent for document: {doc_id}")
        ranking = PageBm25Index(records, k1=k1, b=b).search(question["question"], 3)
        retrieved_pages = [result.page for result in ranking]
        if retrieved_pages != item.get("bm25_top3_pages"):
            raise ValueError(f"recomputed retrieval mismatch: {question_id}")

        if is_answerable:
            evidences = question.get("evidences")
            if not isinstance(evidences, list) or not evidences:
                raise ValueError(f"answerable evidences are invalid: {question_id}")
            oracle_pages = sorted({evidence.get("page") for evidence in evidences})
        else:
            oracle_pages = []
        if oracle_pages != item.get("oracle_pages"):
            raise ValueError(f"Oracle-page mismatch: {question_id}")

        closed, real, oracle = build_reasoning_triplet(
            question,
            records,
            retrieved_pages,
            top_k=3,
        )
        built.append((pilot_id, closed, real, oracle))
    return built


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--split-manifest", required=True, type=Path)
    parser.add_argument("--retrieval-results", required=True, type=Path)
    parser.add_argument("--page-record-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    split_manifest = json.loads(args.split_manifest.read_text(encoding="utf-8"))
    retrieval = json.loads(args.retrieval_results.read_text(encoding="utf-8"))
    expected_retrieval_hash = selection.get("source_sha256", {}).get("retrieval_results")
    if expected_retrieval_hash != sha256_file(args.retrieval_results):
        raise ValueError("retrieval-result checksum differs from frozen selection")
    if retrieval.get("split") != "development_tune":
        raise ValueError("retrieval result is not development_tune")
    configuration = retrieval.get("configuration")
    if not isinstance(configuration, dict):
        raise ValueError("retrieval configuration is missing")
    tune_section = split_manifest.get("development_tune")
    if not isinstance(tune_section, dict) or not isinstance(
        tune_section.get("question_ids"), list
    ):
        raise ValueError("development_tune question IDs are missing")
    tune_ids = set(tune_section["question_ids"])
    questions = {
        item["id"]: item
        for item in load_records(args.benchmark, split="dev")
        if item["id"] in tune_ids
    }
    doc_ids = [item["doc_id"] for item in selection["questions"]]
    page_records = {
        doc_id: read_page_records_jsonl(args.page_record_dir / f"{doc_id}.jsonl")
        for doc_id in doc_ids
    }
    triplets = build_pilot_triplets(
        selection,
        questions,
        page_records,
        tune_question_ids=tune_ids,
        k1=configuration["k1"],
        b=configuration["b"],
    )
    preview = {
        "mode": "execute" if args.execute else "dry_run",
        "paid_request_sent": False,
        "case_count": len(triplets),
        "conditions": ["closed_book", "real_retrieval", "oracle_page"],
        "input_file_count": len(triplets) * 3,
        "selection_sha256": sha256_file(args.selection),
        "output_dir": str(args.output_dir),
    }
    if not args.execute:
        print(json.dumps(preview, indent=2))
        return
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty output dir: {args.output_dir}")

    manifest_cases = []
    for pilot_id, closed, real, oracle in triplets:
        case_dir = args.output_dir / pilot_id
        condition_records = {}
        for name, reasoning_input in (
            ("closed_book", closed),
            ("real_retrieval", real),
            ("oracle_page", oracle),
        ):
            output_path = case_dir / f"{name}.json"
            experiment_record = reasoning_input.to_experiment_record()
            serialized = json.dumps(experiment_record, ensure_ascii=False)
            for forbidden in ("answer_text", '"facts"', '"evidences"'):
                if forbidden in serialized:
                    raise ValueError(f"answer-bearing field leaked into {pilot_id}/{name}")
            write_json(output_path, experiment_record)
            condition_records[name] = {
                "path": str(output_path),
                "sha256": sha256_file(output_path),
                "pages": [page.page for page in reasoning_input.evidence],
                "evidence_characters": sum(
                    len(page.text) for page in reasoning_input.evidence
                ),
            }
        manifest_cases.append({
            "pilot_id": pilot_id,
            "question_id": real.question_id,
            **condition_records,
        })
    manifest = {
        "schema_version": 1,
        "status": "offline_inputs_ready",
        "paid_request_sent": False,
        "selection_sha256": sha256_file(args.selection),
        "retrieval_results_sha256": sha256_file(args.retrieval_results),
        "split_manifest_sha256": sha256_file(args.split_manifest),
        "case_count": len(triplets),
        "conditions": preview["conditions"],
        "input_file_count": len(triplets) * 3,
        "cases": manifest_cases,
    }
    manifest_path = args.output_dir / "manifest.json"
    write_json(manifest_path, manifest)
    preview["manifest"] = str(manifest_path)
    preview["manifest_sha256"] = sha256_file(manifest_path)
    print(json.dumps(preview, indent=2))


if __name__ == "__main__":
    main()
