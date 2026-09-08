"""Build a no-answer-leakage C4 Oracle Facts reasoning input."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .io import sha256_file, write_json


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _load_question(benchmark_path: Path, question_id: str) -> dict[str, Any]:
    records = json.loads(benchmark_path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("benchmark must be a JSON list")
    matches = [record for record in records if record.get("id") == question_id]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one benchmark record for {question_id}")
    return matches[0]


def build_oracle_facts_record(
    oracle_page_record: dict[str, Any], benchmark_record: dict[str, Any]
) -> dict[str, Any]:
    """Select fact text and source pages without copying the benchmark answer."""
    question_id = oracle_page_record.get("question_id")
    if oracle_page_record.get("condition") != "oracle_page":
        raise ValueError("source input must be an oracle_page record")
    if benchmark_record.get("id") != question_id:
        raise ValueError("benchmark question id does not match source input")

    model_input = oracle_page_record.get("model_input")
    facts = benchmark_record.get("facts")
    evidences = benchmark_record.get("evidences")
    if not isinstance(model_input, dict):
        raise ValueError("source model_input is required")
    if not isinstance(facts, list) or not facts:
        raise ValueError("benchmark facts must be a non-empty list")
    if not isinstance(evidences, list) or not evidences:
        raise ValueError("benchmark evidences must be a non-empty list")

    page_by_evidence_id: dict[str, int] = {}
    for evidence in evidences:
        if not isinstance(evidence, dict):
            raise ValueError("each benchmark evidence must be an object")
        local_id = evidence.get("local_id")
        page = evidence.get("page")
        if not isinstance(local_id, str) or not local_id:
            raise ValueError("evidence local_id must be a non-empty string")
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise ValueError("evidence page must be a positive integer")
        if local_id in page_by_evidence_id:
            raise ValueError(f"duplicate evidence local_id: {local_id}")
        page_by_evidence_id[local_id] = page

    fact_evidence: list[dict[str, Any]] = []
    for fact in facts:
        if not isinstance(fact, dict):
            raise ValueError("each benchmark fact must be an object")
        evidence_id = fact.get("evidence_local_id")
        text = fact.get("text_description")
        if evidence_id not in page_by_evidence_id:
            raise ValueError(f"fact references unknown evidence: {evidence_id}")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("fact text_description must be a non-empty string")
        fact_evidence.append(
            {
                "page": page_by_evidence_id[evidence_id],
                "text": text.strip(),
            }
        )

    return {
        "schema_version": 1,
        "question_id": question_id,
        "doc_id": oracle_page_record.get("doc_id"),
        "condition": "oracle_facts",
        "evidence_pages": list(
            dict.fromkeys(item["page"] for item in fact_evidence)
        ),
        "model_input": {
            "instructions": model_input.get("instructions"),
            "question": model_input.get("question"),
            "evidence": fact_evidence,
            "response_schema": model_input.get("response_schema"),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oracle-page-input", required=True, type=Path)
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--question-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable input: {args.output}")
    oracle_page_record = _read_object(args.oracle_page_input)
    if oracle_page_record.get("question_id") != args.question_id:
        raise ValueError("question id does not match Oracle Page input")
    record = build_oracle_facts_record(
        oracle_page_record,
        _load_question(args.benchmark, args.question_id),
    )
    write_json(args.output, record)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "question_id": record["question_id"],
                "condition": record["condition"],
                "fact_count": len(record["model_input"]["evidence"]),
                "output_sha256": sha256_file(args.output),
                "paid_request_sent": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
