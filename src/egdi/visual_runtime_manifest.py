"""Build a label-free R1 visual retrieval manifest from a frozen RRF run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .access import require_evaluation_split_access
from .corpus import read_page_records_jsonl
from .io import sha256_file, write_json
from .visual_routing import ROUTE_LOCAL_VISUAL
from .visual_routing_v1 import ROUTING_POLICY_VERSION, choose_visual_route_v1


FORBIDDEN_RUNTIME_KEYS = {
    "answer",
    "answer_text",
    "is_answerable",
    "gold_pages",
    "evidences",
    "facts",
    "bbox",
    "scores",
    "slices",
}


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            key in FORBIDDEN_RUNTIME_KEYS or _contains_forbidden_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def build_visual_runtime_manifest(
    rrf_run: dict[str, Any],
    *,
    page_records_dir: Path,
    candidate_depth: int = 10,
) -> dict[str, Any]:
    """Project RRF questions to the fields allowed during blind visual ranking."""
    split = rrf_run.get("split")
    if split not in {"development_tune", "development_calibration", "locked_test"}:
        raise ValueError("unknown evaluation split")
    require_evaluation_split_access(split)
    if isinstance(candidate_depth, bool) or not isinstance(candidate_depth, int) or candidate_depth < 1:
        raise ValueError("candidate_depth must be a positive integer")
    source = rrf_run.get("per_question")
    if not isinstance(source, list) or not source:
        raise ValueError("RRF run must contain per_question records")

    records_by_doc: dict[str, Any] = {}
    questions: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in source:
        question_id = item.get("question_id")
        question = item.get("question")
        doc_id = item.get("doc_id")
        pages = item.get("retrieved_pages")
        if not all(isinstance(value, str) and value for value in (question_id, question, doc_id)):
            raise ValueError("RRF records require question_id, question, and doc_id")
        if question_id in seen_ids:
            raise ValueError(f"duplicate question_id: {question_id}")
        seen_ids.add(question_id)
        if not isinstance(pages, list) or len(pages) < candidate_depth:
            raise ValueError(f"RRF ranking is shorter than candidate_depth: {question_id}")
        candidates = pages[:candidate_depth]
        if any(isinstance(page, bool) or not isinstance(page, int) or page < 1 for page in candidates):
            raise ValueError("retrieved_pages must contain positive integers")
        if len(candidates) != len(set(candidates)):
            raise ValueError("retrieved_pages must be unique within candidate depth")

        if doc_id not in records_by_doc:
            records_by_doc[doc_id] = read_page_records_jsonl(
                page_records_dir / f"{doc_id}.jsonl"
            )
        route = choose_visual_route_v1(question, records_by_doc[doc_id])
        if route["route"] != ROUTE_LOCAL_VISUAL:
            continue
        questions.append(
            {
                "question_id": question_id,
                "question": question,
                "doc_id": doc_id,
                "candidate_pages": candidates,
                "matched_visual_cue": route["matched_signal"],
            }
        )

    manifest = {
        "schema_version": 1,
        "split": split,
        "purpose": "blind_question_conditioned_visual_page_ranking",
        "routing_policy_version": ROUTING_POLICY_VERSION,
        "candidate_source": "frozen_equal_weight_bm25_dense_rrf",
        "candidate_depth": candidate_depth,
        "question_count": len(questions),
        "document_count": len({item["doc_id"] for item in questions}),
        "unique_candidate_page_count": len(
            {(item["doc_id"], page) for item in questions for page in item["candidate_pages"]}
        ),
        "contains_gold_or_answer_labels": False,
        "questions": questions,
    }
    if not questions:
        raise ValueError("RRF run contains no R1 questions")
    if _contains_forbidden_key(manifest):
        raise ValueError("runtime manifest contains a forbidden evaluation field")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rrf-run", required=True, type=Path)
    parser.add_argument("--page-records-dir", required=True, type=Path)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--candidate-depth", type=int, default=10)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable output: {args.output}")

    run = json.loads(args.rrf_run.read_text(encoding="utf-8"))
    manifest = build_visual_runtime_manifest(
        run,
        page_records_dir=args.page_records_dir,
        candidate_depth=args.candidate_depth,
    )
    manifest["source_sha256"] = {
        "rrf_run": sha256_file(args.rrf_run),
        "protocol": sha256_file(args.protocol),
    }
    write_json(args.output, manifest)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "output_sha256": sha256_file(args.output),
                "question_count": manifest["question_count"],
                "document_count": manifest["document_count"],
                "unique_candidate_page_count": manifest["unique_candidate_page_count"],
                "contains_gold_or_answer_labels": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
