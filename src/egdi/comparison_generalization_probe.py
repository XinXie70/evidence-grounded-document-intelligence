"""Probe existing structural selectors on held-out development questions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from .comparison_consistency import compute_comparison
from .comparison_contract import adapt_selection
from .continued_enrollment_table import select_continued_enrollment_facts
from .io import sha256_file, write_json
from .qualified_metric_selector import select_qualified_metric_facts


_SELECTORS: dict[str, Callable[[str, Mapping[int, str]], list[Any]]] = {
    "continued_enrollment_table_v0": select_continued_enrollment_facts,
    "continued_enrollment_table_v1": select_continued_enrollment_facts,
    "qualified_metric_selector_v0": select_qualified_metric_facts,
    "qualified_metric_selector_v1": select_qualified_metric_facts,
}


def _load_pages(path: Path, candidates: list[int]) -> dict[int, str]:
    if not candidates or any(
        not isinstance(page, int) or isinstance(page, bool) or page < 1
        for page in candidates
    ):
        raise ValueError("candidate_pages must contain positive integers")
    wanted = set(candidates)
    records: dict[int, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("page") in wanted:
            records[record["page"]] = record.get("text", "")
    missing = wanted - records.keys()
    if missing:
        raise ValueError(f"page records omit candidates: {sorted(missing)}")
    return records


def probe_manifest(manifest: dict[str, Any], *, root: Path) -> dict[str, Any]:
    if manifest.get("split") != "development_tune":
        raise ValueError("probe is restricted to split=development_tune")
    if manifest.get("uses_gold_answer") is not False:
        raise ValueError("manifest must declare uses_gold_answer=false")
    if manifest.get("uses_gold_evidence_pages") is not False:
        raise ValueError("manifest must declare uses_gold_evidence_pages=false")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("manifest cases must be a non-empty list")

    outputs = []
    seen: set[str] = set()
    for case in cases:
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            raise ValueError("case_id must be non-empty and unique")
        seen.add(case_id)
        selector_id = case.get("selector_version")
        selector = _SELECTORS.get(selector_id)
        if selector is None:
            raise ValueError(f"unsupported selector in probe: {selector_id!r}")
        page_path = root / case["page_records"]
        pages = _load_pages(page_path, case["candidate_pages"])
        record = {
            "case_id": case_id,
            "question_id": case["question_id"],
            "doc_id": case["doc_id"],
            "question": case["question"],
            "selector_version": selector_id,
            "candidate_pages": case["candidate_pages"],
            "page_records_sha256": sha256_file(page_path),
        }
        try:
            facts = selector(case["question"], pages)
        except ValueError as error:
            record.update({"status": "unsupported", "reason": str(error)})
        else:
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
            record.update(
                {
                    "status": "success",
                    "selected_facts": selected_facts,
                    "comparison_contract": contract,
                    "deterministic_comparison": compute_comparison(
                        [
                            {"value": contract[side]["value"], "unit": contract[side]["unit"]}
                            for side in ("left", "right")
                        ]
                    ),
                }
            )
        outputs.append(record)

    successes = sum(record["status"] == "success" for record in outputs)
    return {
        "schema_version": 1,
        "experiment_type": "held_out_comparison_generalization_probe",
        "split": "development_tune",
        "cases": outputs,
        "summary": {
            "case_count": len(outputs),
            "success_count": successes,
            "unsupported_count": len(outputs) - successes,
            "success_rate": successes / len(outputs),
            "paid_api_used": False,
        },
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
        raise FileExistsError(f"refusing to overwrite immutable probe: {args.output}")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    result = probe_manifest(manifest, root=Path.cwd())
    result["manifest_sha256"] = sha256_file(args.manifest)
    write_json(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
