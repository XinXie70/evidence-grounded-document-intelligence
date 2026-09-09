"""Prepare immutable generic fact-extraction inputs from a frozen case selection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .comparison_fact_input import build_fact_input
from .io import sha256_file, write_json


def prepare_inputs(
    selection: dict[str, Any], *, output_dir: Path
) -> dict[str, Any]:
    cases = selection.get("cases")
    if not isinstance(cases, list) or len(cases) != selection.get("case_count"):
        raise ValueError("selection case count does not match cases")
    if selection.get("leakage_controls", {}).get("uses_gold_answer") is not False:
        raise ValueError("selection must be answer-label-free")
    if selection.get("leakage_controls", {}).get("uses_gold_evidence_pages") is not False:
        raise ValueError("selection must be evidence-label-free")

    manifest_cases = []
    for case in cases:
        case_id = case.get("case_id")
        page_records_value = case.get("page_records")
        if not isinstance(case_id, str) or not isinstance(page_records_value, str):
            raise ValueError("selected case is incomplete")
        case_dir = output_dir / case_id
        case_path = case_dir / "case.json"
        input_path = case_dir / "input.json"
        if case_path.exists() or input_path.exists():
            raise FileExistsError(f"refusing to overwrite prepared case: {case_id}")
        write_json(case_path, case)
        prepared = build_fact_input(case, Path(page_records_value))
        prepared["source_case_sha256"] = sha256_file(case_path)
        write_json(input_path, prepared)
        manifest_cases.append({
            "case_id": case_id,
            "question_id": case["question_id"],
            "input_path": str(input_path),
            "input_sha256": sha256_file(input_path),
        })
    return {
        "schema_version": 1,
        "experiment_id": "day6_frozen_generic_comparison_validation_v0",
        "selection_split": "development_tune",
        "case_count": len(manifest_cases),
        "cases": manifest_cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    if args.manifest.exists():
        raise FileExistsError(f"refusing to overwrite input manifest: {args.manifest}")
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    manifest = prepare_inputs(selection, output_dir=args.output_dir)
    manifest["selection_sha256"] = sha256_file(args.selection)
    write_json(args.manifest, manifest)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
