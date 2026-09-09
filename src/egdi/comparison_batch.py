"""Run heterogeneous comparison selections through one deterministic batch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .comparison_consistency import compute_comparison
from .comparison_contract import adapt_selection
from .io import sha256_file, write_json


def _selection_facts(contract: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"value": contract[side]["value"], "unit": contract[side]["unit"]}
        for side in ("left", "right")
    ]


def run_manifest(manifest: dict[str, Any], *, root: Path) -> dict[str, Any]:
    if manifest.get("split") != "development_tune":
        raise ValueError("batch is restricted to split=development_tune")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("manifest entries must be a non-empty list")

    records = []
    seen_ids: set[str] = set()
    for entry in entries:
        case_id = entry.get("case_id")
        source = entry.get("selection")
        if not isinstance(case_id, str) or not case_id or case_id in seen_ids:
            raise ValueError("case_id must be non-empty and unique")
        if not isinstance(source, str) or not source:
            raise ValueError("each entry must contain a selection path")
        seen_ids.add(case_id)
        path = root / source
        selection = json.loads(path.read_text(encoding="utf-8"))
        contract = adapt_selection(selection)
        records.append(
            {
                "case_id": case_id,
                "source_selection": source,
                "source_selection_sha256": sha256_file(path),
                "contract": contract,
                "deterministic_comparison": compute_comparison(
                    _selection_facts(contract)
                ),
            }
        )

    retrieval_eligible = sum(
        item["contract"]["evaluation_eligibility"]["evidence_retrieval"] == "eligible"
        for item in records
    )
    reasoning_eligible = sum(
        item["contract"]["evaluation_eligibility"]["grounded_reasoning"] == "eligible"
        for item in records
    )
    return {
        "schema_version": 1,
        "experiment_type": "unified_comparison_batch",
        "split": "development_tune",
        "records": records,
        "summary": {
            "case_count": len(records),
            "processed_count": len(records),
            "grounded_reasoning_eligible_count": reasoning_eligible,
            "evidence_retrieval_eligible_count": retrieval_eligible,
            "paid_api_used": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable batch result: {args.output}")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    result = run_manifest(manifest, root=Path.cwd())
    result["manifest_sha256"] = sha256_file(args.manifest)
    write_json(args.output, result)
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
