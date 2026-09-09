"""Repair unsupported numeric fact citations using supplied evidence only."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from .io import sha256_file, write_json


def repair_citations(
    finalized: dict[str, Any], citation_audit: dict[str, Any]
) -> dict[str, Any]:
    """Keep supported citations and repair only unsupported numeric citations."""
    leakage = finalized.get("leakage_controls", {})
    if leakage.get("uses_gold_answer") is not False:
        raise ValueError("finalized predictions are not answer-label-free")
    if leakage.get("uses_gold_evidence_pages") is not False:
        raise ValueError("finalized predictions are not evidence-label-free")
    if citation_audit.get("uses_benchmark_labels") is not False:
        raise ValueError("citation audit used benchmark labels")

    audit_by_id = {item.get("case_id"): item for item in citation_audit.get("cases", [])}
    source_cases = finalized.get("cases", [])
    if not isinstance(source_cases, list) or not source_cases:
        raise ValueError("finalized predictions have no cases")
    repaired_cases = []
    repair_count = 0
    rejected_count = 0
    abstained_count = 0
    for source_case in source_cases:
        case = copy.deepcopy(source_case)
        case_id = case.get("case_id")
        audit = audit_by_id.get(case_id)
        if audit is None or audit.get("question_id") != case.get("question_id"):
            raise ValueError(f"missing or mismatched citation audit: {case_id}")
        facts = case.get("selected_facts")
        audited_facts = audit.get("facts")
        if not isinstance(facts, list) or not isinstance(audited_facts, list):
            raise ValueError(f"case facts are invalid: {case_id}")
        if len(facts) != len(audited_facts):
            raise ValueError(f"fact count mismatch: {case_id}")

        unsupported_indices = [
            index
            for index, item in enumerate(audited_facts)
            if not item.get("value_occurs_on_a_cited_page")
        ]
        repair_record = {
            "policy": "preserve_supported_else_earliest_common_physical_page_v0",
            "status": "not_needed",
            "changes": [],
        }
        if case.get("status") == "unsupported":
            repair_record["status"] = "not_applicable_abstained"
            abstained_count += 1
        elif unsupported_indices:
            support_sets = [
                set(audited_facts[index].get("value_occurs_on_supplied_pages", []))
                for index in unsupported_indices
            ]
            if any(not pages for pages in support_sets):
                case["status"] = "unsupported"
                repair_record["status"] = "rejected_no_supporting_page"
                rejected_count += 1
            else:
                common_pages = set.intersection(*support_sets)
                shared_page = min(common_pages) if common_pages else None
                for index in unsupported_indices:
                    candidates = audited_facts[index]["value_occurs_on_supplied_pages"]
                    repaired_page = shared_page if shared_page is not None else min(candidates)
                    original_pages = list(facts[index]["cited_pages"])
                    facts[index]["cited_pages"] = [repaired_page]
                    facts[index]["selection_basis"] = (
                        "model_extraction_then_numeric_occurrence_citation_repair"
                    )
                    repair_record["changes"].append({
                        "fact_index": index,
                        "original_cited_pages": original_pages,
                        "repaired_cited_pages": [repaired_page],
                        "candidate_support_pages": candidates,
                    })
                repair_record["status"] = "repaired"
                repair_record["used_shared_support_page"] = shared_page is not None
                repair_count += 1
        case["citation_repair"] = repair_record
        repaired_cases.append(case)

    if len(repaired_cases) != len(source_cases):
        raise AssertionError("citation repair lost cases")
    return {
        "schema_version": 1,
        "experiment_type": "citation_repaired_model_extracted_comparison_batch",
        "split": "development_tune",
        "cases": repaired_cases,
        "summary": {
            "case_count": len(repaired_cases),
            "repaired_case_count": repair_count,
            "rejected_case_count": rejected_count,
            "abstained_case_count": abstained_count,
            "unchanged_case_count": (
                len(repaired_cases) - repair_count - rejected_count - abstained_count
            ),
        },
        "leakage_controls": {
            "uses_gold_answer": False,
            "uses_gold_evidence_pages": False,
            "runtime_uses_benchmark_labels": False,
            "policy_designed_after_development_failure": True,
        },
        "paid_api_used": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--finalized", required=True, type=Path)
    parser.add_argument("--citation-audit", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable repair: {args.output}")
    finalized = json.loads(args.finalized.read_text(encoding="utf-8"))
    citation_audit = json.loads(args.citation_audit.read_text(encoding="utf-8"))
    result = repair_citations(finalized, citation_audit)
    result["source_finalized_sha256"] = sha256_file(args.finalized)
    result["source_citation_audit_sha256"] = sha256_file(args.citation_audit)
    write_json(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
