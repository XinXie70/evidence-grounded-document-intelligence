"""Build a label-free structured fact-extraction request from retrieved pages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .io import sha256_file, write_json


RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "facts"],
    "properties": {
        "status": {"type": "string", "enum": ["extracted", "insufficient_evidence"]},
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["label", "metric", "value", "unit", "cited_pages"],
                "properties": {
                    "label": {"type": "string"},
                    "metric": {"type": "string"},
                    "value": {"type": "string"},
                    "unit": {"type": "string"},
                    "cited_pages": {"type": "array", "items": {"type": "integer"}},
                },
            },
        },
    },
}


INSTRUCTIONS = """Use only the supplied document evidence. Extract exactly two ordered numeric facts needed to answer the comparison question. The first fact must correspond to the first quantity named in the question and the second fact to the second quantity. Do not calculate the difference and do not use outside knowledge. Preserve a shared, explicit unit. Cite only physical PDF pages supplied here. If both facts cannot be identified unambiguously, return status insufficient_evidence with an empty facts list."""


def build_fact_input(case: dict[str, Any], page_records: Path) -> dict[str, Any]:
    candidates = case.get("candidate_pages")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("case candidate_pages must be a non-empty list")
    wanted = set(candidates)
    retrieval_method = case.get("retrieval_method")
    if not isinstance(retrieval_method, str) or not retrieval_method:
        raise ValueError("case retrieval_method must be a non-empty string")
    expected_suffix = f"top{len(candidates)}"
    if not retrieval_method.casefold().endswith(expected_suffix):
        raise ValueError("retrieval_method top-k does not match candidate page count")
    pages = {}
    for line in page_records.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("page") in wanted:
            pages[record["page"]] = record.get("text", "")
    if wanted != pages.keys():
        raise ValueError("page records omit requested evidence pages")
    evidence = [{"page": page, "text": pages[page]} for page in candidates]
    return {
        "schema_version": 1,
        "question_id": case["question_id"],
        "doc_id": case["doc_id"],
        "condition": "real_retrieval_fact_extraction",
        "evidence_pages": candidates,
        "model_input": {
            "instructions": INSTRUCTIONS,
            "question": case["question"],
            "evidence": evidence,
            "response_schema": RESPONSE_SCHEMA,
        },
        "retrieval_method": retrieval_method,
        "uses_gold_answer": False,
        "uses_gold_evidence_pages": False,
        "page_records_sha256": sha256_file(page_records),
        "paid_api_used": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, type=Path)
    parser.add_argument("--page-records", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable input: {args.output}")
    case = json.loads(args.case.read_text(encoding="utf-8"))
    result = build_fact_input(case, args.page_records)
    result["source_case_sha256"] = sha256_file(args.case)
    write_json(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
