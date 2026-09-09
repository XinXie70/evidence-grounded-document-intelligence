"""Route comparison questions across the existing text-selector library."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from .balance_sheet_selector import select_balance_sheet_facts
from .comparison_consistency import compute_comparison
from .comparison_contract import adapt_selection
from .continued_enrollment_table import select_continued_enrollment_facts
from .interest_method_selector import select_interest_method_facts
from .io import sha256_file, write_json
from .list_count_selector import select_list_count_facts
from .product_dimension_selector import select_product_depth_facts
from .qualified_metric_selector import select_qualified_metric_facts


_SELECTORS: dict[str, Callable[[str, Mapping[int, str]], list[Any]]] = {
    "balance_sheet_selector_v0": select_balance_sheet_facts,
    "continued_enrollment_table_v1": select_continued_enrollment_facts,
    "interest_method_selector_v0": select_interest_method_facts,
    "list_count_selector_v1_excludes_reference_sections": select_list_count_facts,
    "product_dimension_selector_v0": select_product_depth_facts,
    "qualified_metric_selector_v1": select_qualified_metric_facts,
}


def _load_pages(path: Path, candidates: list[int]) -> dict[int, str]:
    wanted = set(candidates)
    if not wanted or len(wanted) != len(candidates):
        raise ValueError("candidate_pages must be non-empty and unique")
    pages = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("page") in wanted:
            pages[record["page"]] = record.get("text", "")
    if wanted != pages.keys():
        raise ValueError(f"page records omit candidates: {sorted(wanted - pages.keys())}")
    return pages


def route_case(case: dict[str, Any], pages: Mapping[int, str]) -> dict[str, Any]:
    """Accept exactly one successful selector; abstain on zero or ambiguity."""
    successes = []
    rejections = {}
    for selector_id, selector in _SELECTORS.items():
        try:
            facts = selector(case["question"], pages)
        except ValueError as error:
            rejections[selector_id] = str(error)
        else:
            successes.append((selector_id, facts))
    if not successes:
        return {"status": "unsupported", "selector_rejections": rejections}
    if len(successes) > 1:
        return {
            "status": "ambiguous",
            "successful_selectors": [selector_id for selector_id, _ in successes],
            "selector_rejections": rejections,
        }
    selector_id, facts = successes[0]
    selected_facts = [fact.to_dict() for fact in facts]
    contract = adapt_selection(
        {
            "question_id": case["question_id"],
            "doc_id": case["doc_id"],
            "question": case["question"],
            "selector_version": selector_id,
            "selected_facts": selected_facts,
            "uses_gold_answer": False,
            "uses_gold_evidence_pages": False,
        }
    )
    comparison = compute_comparison(
        [{"value": contract[side]["value"], "unit": contract[side]["unit"]}
         for side in ("left", "right")]
    )
    return {
        "status": "success",
        "selected_selector": selector_id,
        "selected_facts": selected_facts,
        "comparison_contract": contract,
        "deterministic_comparison": comparison,
        "selector_rejections": rejections,
    }


def route_manifest(manifest: dict[str, Any], *, root: Path) -> dict[str, Any]:
    if manifest.get("split") != "development_tune":
        raise ValueError("router is restricted to split=development_tune")
    if manifest.get("uses_gold_answer") is not False:
        raise ValueError("manifest must declare uses_gold_answer=false")
    if manifest.get("uses_gold_evidence_pages") is not False:
        raise ValueError("manifest must declare uses_gold_evidence_pages=false")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("manifest cases must be a non-empty list")
    outputs = []
    seen = set()
    for case in cases:
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            raise ValueError("case_id must be non-empty and unique")
        seen.add(case_id)
        page_path = root / case["page_records"]
        routed = route_case(case, _load_pages(page_path, case["candidate_pages"]))
        outputs.append(
            {
                "case_id": case_id,
                "question_id": case["question_id"],
                "doc_id": case["doc_id"],
                "question": case["question"],
                "candidate_pages": case["candidate_pages"],
                "page_records_sha256": sha256_file(page_path),
                **routed,
            }
        )
    status_counts = {
        status: sum(case["status"] == status for case in outputs)
        for status in ("success", "unsupported", "ambiguous")
    }
    return {
        "schema_version": 1,
        "experiment_type": "automatic_comparison_selector_routing",
        "split": "development_tune",
        "cases": outputs,
        "summary": {"case_count": len(outputs), **status_counts, "paid_api_used": False},
        "leakage_controls": {
            "uses_gold_answer": False,
            "uses_gold_evidence_pages": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable route result: {args.output}")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    result = route_manifest(manifest, root=Path.cwd())
    result["manifest_sha256"] = sha256_file(args.manifest)
    write_json(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
