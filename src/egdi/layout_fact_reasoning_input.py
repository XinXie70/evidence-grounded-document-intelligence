"""Build a grounded-reasoning input from automatically selected layout facts."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from .io import sha256_file, write_json


def build_layout_fact_reasoning_record(
    selection: dict[str, Any], template: dict[str, Any]
) -> dict[str, Any]:
    """Adapt selected facts to the condition-blind reasoning contract."""
    if selection.get("question_id") != template.get("question_id"):
        raise ValueError("selection and template question ids must match")
    if selection.get("doc_id") != template.get("doc_id"):
        raise ValueError("selection and template document ids must match")
    if selection.get("uses_gold_answer_or_gold_facts") is not False:
        raise ValueError("selection must explicitly exclude gold answers and gold facts")
    facts = selection.get("selected_facts")
    model_input = template.get("model_input")
    if not isinstance(facts, list) or not facts:
        raise ValueError("selection must contain selected_facts")
    if not isinstance(model_input, dict):
        raise ValueError("template must contain model_input")

    evidence = []
    pages = []
    for fact in facts:
        if not isinstance(fact, dict):
            raise ValueError("each selected fact must be an object")
        page = fact.get("page")
        title = fact.get("table_title")
        unit = fact.get("unit")
        row = fact.get("row")
        columns = fact.get("column_path")
        value = fact.get("value")
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise ValueError("selected fact page must be a positive integer")
        if not all(isinstance(item, str) and item.strip() for item in (title, unit, row, value)):
            raise ValueError("selected fact title, unit, row, and value must be non-empty strings")
        if not isinstance(columns, list) or not columns or not all(
            isinstance(item, str) and item.strip() for item in columns
        ):
            raise ValueError("selected fact column_path must contain strings")
        text = (
            f"Table: {title}\n"
            f"Unit: {unit}\n"
            f"Row: {row}\n"
            f"Column: {' -> '.join(columns)}\n"
            f"Value: {value}"
        )
        evidence.append({"page": page, "text": text})
        pages.append(page)

    return {
        "schema_version": 1,
        "question_id": selection["question_id"],
        "doc_id": selection["doc_id"],
        "condition": "layout_facts",
        "evidence_pages": list(dict.fromkeys(pages)),
        "model_input": {
            "instructions": copy.deepcopy(model_input.get("instructions")),
            "question": copy.deepcopy(model_input.get("question")),
            "evidence": evidence,
            "response_schema": copy.deepcopy(model_input.get("response_schema")),
        },
        "evidence_provenance": {
            "method": "question_guided_layout_fact_selection_v0",
            "uses_gold_pages": True,
            "uses_gold_answer_or_gold_facts": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable input: {args.output}")
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    template = json.loads(args.template.read_text(encoding="utf-8"))
    record = build_layout_fact_reasoning_record(selection, template)
    record["evidence_provenance"]["selection_sha256"] = sha256_file(args.selection)
    record["evidence_provenance"]["template_sha256"] = sha256_file(args.template)
    write_json(args.output, record)
    print(json.dumps({
        "output": str(args.output),
        "question_id": record["question_id"],
        "evidence_pages": record["evidence_pages"],
        "fact_count": len(record["model_input"]["evidence"]),
        "paid_request_sent": False,
        "output_sha256": sha256_file(args.output),
    }, indent=2))


if __name__ == "__main__":
    main()
