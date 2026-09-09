"""Verify that extracted numeric facts actually occur on their cited evidence pages."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from .comparison_consistency import parse_decimal_value
from .io import sha256_file, write_json


_TEXT_NUMBER = re.compile(
    r"(?<![A-Za-z0-9])(?:\(\d[\d,]*(?:\.\d+)?\)|[-+]?\d[\d,]*(?:\.\d+)?)"
    r"(?![A-Za-z0-9])"
)


def _canonical_number(value: str) -> str:
    number = parse_decimal_value(value)
    rendered = format(number, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return "0" if rendered in {"-0", ""} else rendered


def numeric_values_in_text(text: str) -> set[str]:
    """Return canonical values for well-formed numeric strings observed in text."""
    values: set[str] = set()
    for match in _TEXT_NUMBER.finditer(text):
        try:
            values.add(_canonical_number(match.group(0)))
        except ValueError:
            continue
    return values


def audit_fact_citations(
    model_input: dict[str, Any], result: dict[str, Any]
) -> dict[str, Any]:
    """Check value occurrence without consulting benchmark labels."""
    for key in ("question_id", "doc_id", "evidence_pages"):
        if model_input.get(key) != result.get(key):
            raise ValueError(f"input/result {key} mismatch")
    evidence = model_input.get("model_input", {}).get("evidence")
    if not isinstance(evidence, list):
        raise ValueError("model input evidence must be a list")
    page_text: dict[int, str] = {}
    for item in evidence:
        if not isinstance(item, dict):
            raise ValueError("evidence item must be an object")
        page = item.get("page")
        text = item.get("text")
        if isinstance(page, bool) or not isinstance(page, int) or not isinstance(text, str):
            raise ValueError("evidence item must contain an integer page and string text")
        page_text[page] = text

    output = result.get("output", {})
    facts = output.get("facts")
    if output.get("status") == "insufficient_evidence" and facts == []:
        return {
            "question_id": result["question_id"],
            "doc_id": result["doc_id"],
            "extraction_status": "insufficient_evidence",
            "facts": [],
            "all_facts_supported_by_citations": True,
            "eligible_for_answer_acceptance": False,
            "policy_action": "abstain_no_extracted_facts",
            "uses_benchmark_labels": False,
        }
    if output.get("status") != "extracted" or not isinstance(facts, list) or len(facts) != 2:
        raise ValueError("audit requires exactly two extracted facts")

    page_values = {page: numeric_values_in_text(text) for page, text in page_text.items()}
    audited_facts = []
    for index, fact in enumerate(facts):
        if not isinstance(fact, dict):
            raise ValueError("fact must be an object")
        canonical_value = _canonical_number(fact.get("value"))
        cited_pages = fact.get("cited_pages")
        if not isinstance(cited_pages, list) or not cited_pages:
            raise ValueError("fact must cite at least one page")
        unknown_pages = sorted(set(cited_pages) - set(page_text))
        if unknown_pages:
            raise ValueError(f"fact cites pages absent from input: {unknown_pages}")
        supported_citations = [
            page for page in cited_pages if canonical_value in page_values[page]
        ]
        supplied_support_pages = [
            page for page in page_text if canonical_value in page_values[page]
        ]
        audited_facts.append({
            "fact_index": index,
            "label": fact.get("label"),
            "reported_value": fact.get("value"),
            "canonical_value": canonical_value,
            "cited_pages": cited_pages,
            "supported_cited_pages": supported_citations,
            "unsupported_cited_pages": [
                page for page in cited_pages if page not in supported_citations
            ],
            "value_occurs_on_a_cited_page": bool(supported_citations),
            "value_occurs_on_supplied_pages": supplied_support_pages,
        })

    accepted = all(item["value_occurs_on_a_cited_page"] for item in audited_facts)
    return {
        "question_id": result["question_id"],
        "doc_id": result["doc_id"],
        "extraction_status": "extracted",
        "facts": audited_facts,
        "all_facts_supported_by_citations": accepted,
        "eligible_for_answer_acceptance": accepted,
        "policy_action": "accept" if accepted else "reject_unverified_citations",
        "uses_benchmark_labels": False,
    }


def audit_batch(manifest: dict[str, Any], *, results_dir: Path) -> dict[str, Any]:
    cases = manifest.get("cases")
    if not isinstance(cases, list) or len(cases) != manifest.get("case_count"):
        raise ValueError("manifest case count does not match cases")
    audits = []
    for item in cases:
        case_id = item["case_id"]
        input_path = Path(item["input_path"])
        result_path = results_dir / case_id / "result.json"
        if sha256_file(input_path) != item.get("input_sha256"):
            raise ValueError(f"input checksum mismatch: {input_path}")
        model_input = json.loads(input_path.read_text(encoding="utf-8"))
        result = json.loads(result_path.read_text(encoding="utf-8"))
        audit = audit_fact_citations(model_input, result)
        audit.update({
            "case_id": case_id,
            "input_sha256": sha256_file(input_path),
            "result_sha256": sha256_file(result_path),
        })
        audits.append(audit)
    accepted_count = sum(item["eligible_for_answer_acceptance"] for item in audits)
    abstention_count = sum(item["extraction_status"] == "insufficient_evidence" for item in audits)
    rejected_count = len(audits) - accepted_count - abstention_count
    return {
        "schema_version": 1,
        "experiment_type": "numeric_fact_citation_support_audit",
        "case_count": len(audits),
        "accepted_count": accepted_count,
        "abstention_count": abstention_count,
        "rejected_count": rejected_count,
        "citation_support_rate": accepted_count / len(audits),
        "cases": audits,
        "uses_benchmark_labels": False,
        "paid_api_used": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable audit: {args.output}")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    audit = audit_batch(manifest, results_dir=args.results_dir)
    audit["manifest_sha256"] = sha256_file(args.manifest)
    write_json(args.output, audit)
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
