"""Finalize a generic fact-extraction batch before post-hoc benchmark scoring."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .comparison_fact_finalize import finalize_fact_result
from .io import sha256_file, write_json


def finalize_batch(
    manifest: dict[str, Any], *, results_dir: Path
) -> dict[str, Any]:
    cases = manifest.get("cases")
    if not isinstance(cases, list) or len(cases) != manifest.get("case_count"):
        raise ValueError("manifest case count does not match cases")

    finalized_cases = []
    source_results = []
    total_cost = 0.0
    for item in cases:
        case_id = item.get("case_id")
        input_path_value = item.get("input_path")
        if not isinstance(case_id, str) or not isinstance(input_path_value, str):
            raise ValueError("manifest case is incomplete")
        input_path = Path(input_path_value)
        if sha256_file(input_path) != item.get("input_sha256"):
            raise ValueError(f"input checksum mismatch: {input_path}")
        result_path = results_dir / case_id / "result.json"
        if not result_path.is_file():
            raise FileNotFoundError(f"missing result: {result_path}")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("input_sha256") != item["input_sha256"]:
            raise ValueError(f"result/input checksum mismatch: {result_path}")
        model_input = json.loads(input_path.read_text(encoding="utf-8"))
        finalized = finalize_fact_result(model_input, result, case_id=case_id)
        finalized_cases.extend(finalized["cases"])
        cost = finalized.get("source_estimated_cost_usd")
        if isinstance(cost, bool) or not isinstance(cost, (int, float)):
            raise ValueError(f"invalid source cost: {result_path}")
        total_cost += cost
        source_results.append({
            "case_id": case_id,
            "input_sha256": item["input_sha256"],
            "result_path": str(result_path),
            "result_sha256": sha256_file(result_path),
        })

    return {
        "schema_version": 1,
        "experiment_type": "finalized_model_extracted_comparison_batch",
        "split": "development_tune",
        "cases": finalized_cases,
        "leakage_controls": {
            "uses_gold_answer": False,
            "uses_gold_evidence_pages": False,
            "benchmark_loaded_during_finalization": False,
        },
        "paid_api_used": True,
        "source_estimated_cost_usd": round(total_cost, 9),
        "source_results": source_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable finalization: {args.output}")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    finalized = finalize_batch(manifest, results_dir=args.results_dir)
    finalized["manifest_sha256"] = sha256_file(args.manifest)
    write_json(args.output, finalized)
    print(json.dumps(finalized, indent=2))


if __name__ == "__main__":
    main()
