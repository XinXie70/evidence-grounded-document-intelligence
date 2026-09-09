"""Finalize validated model-extracted facts with deterministic arithmetic."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .comparison_consistency import compute_comparison
from .comparison_intent import parse_comparison_intent
from .io import sha256_file, write_json
from .reasoning_api import validate_comparison_fact_output


def finalize_fact_result(
    model_input: dict[str, Any], result: dict[str, Any], *, case_id: str
) -> dict[str, Any]:
    for key in ("question_id", "doc_id", "evidence_pages"):
        if model_input.get(key) != result.get(key):
            raise ValueError(f"input/result {key} mismatch")
    current_validation = validate_comparison_fact_output(
        result.get("output", {}), result.get("evidence_pages", [])
    )
    if not current_validation["valid"]:
        raise ValueError("model result did not pass local validation")
    output = result.get("output", {})
    question = model_input["model_input"]["question"]
    if output.get("status") == "insufficient_evidence":
        finalized_case = {
            "case_id": case_id,
            "question_id": model_input["question_id"],
            "doc_id": model_input["doc_id"],
            "question": question,
            "status": "unsupported",
            "operation": parse_comparison_intent(question).operation,
            "selected_facts": [],
            "deterministic_comparison": None,
            "source_response_id": result.get("response_id"),
            "model": result.get("model"),
            "reason": "model_reported_insufficient_evidence",
        }
        return {
            "schema_version": 1,
            "experiment_type": "finalized_model_extracted_comparison",
            "split": "development_tune",
            "cases": [finalized_case],
            "leakage_controls": {
                "uses_gold_answer": False,
                "uses_gold_evidence_pages": False,
            },
            "paid_api_used": True,
            "source_estimated_cost_usd": result.get("call_log", {}).get("estimated_cost"),
        }
    if output.get("status") != "extracted":
        raise ValueError("model result status is invalid")
    facts = output.get("facts")
    if not isinstance(facts, list) or len(facts) != 2:
        raise ValueError("finalizer requires exactly two ordered facts")
    normalized_facts = []
    for fact in facts:
        normalized_facts.append(
            {
                "label": fact["label"],
                "metric": fact["metric"],
                "value": fact["value"],
                "unit": fact["unit"],
                "cited_pages": fact["cited_pages"],
                "selection_basis": "model_extraction_from_label_free_retrieved_pages",
            }
        )
    comparison = compute_comparison(
        [{"value": fact["value"], "unit": fact["unit"]} for fact in normalized_facts]
    )
    return {
        "schema_version": 1,
        "experiment_type": "finalized_model_extracted_comparison",
        "split": "development_tune",
        "cases": [
            {
                "case_id": case_id,
                "question_id": model_input["question_id"],
                "doc_id": model_input["doc_id"],
                "question": question,
                "status": "success",
                "operation": parse_comparison_intent(question).operation,
                "selected_facts": normalized_facts,
                "deterministic_comparison": comparison,
                "source_response_id": result.get("response_id"),
                "model": result.get("model"),
            }
        ],
        "leakage_controls": {
            "uses_gold_answer": False,
            "uses_gold_evidence_pages": False,
        },
        "paid_api_used": True,
        "source_estimated_cost_usd": result.get("call_log", {}).get("estimated_cost"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable finalization: {args.output}")
    model_input = json.loads(args.input.read_text(encoding="utf-8"))
    result = json.loads(args.result.read_text(encoding="utf-8"))
    if result.get("input_sha256") != sha256_file(args.input):
        raise ValueError("result was not generated from this frozen input")
    finalized = finalize_fact_result(model_input, result, case_id=args.case_id)
    finalized["input_sha256"] = sha256_file(args.input)
    finalized["result_sha256"] = sha256_file(args.result)
    write_json(args.output, finalized)
    print(json.dumps(finalized, indent=2))


if __name__ == "__main__":
    main()
