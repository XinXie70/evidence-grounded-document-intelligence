"""Derive a one-judge-type rejudge manifest without changing any judge input."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .io import sha256_file, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--judge-type", choices=("semantic", "support"), default="support")
    args = parser.parse_args()
    source = json.loads(args.source.read_text(encoding="utf-8"))
    cases = []
    for item in source["cases"]:
        cases.append({
            "pilot_id": item["pilot_id"],
            "question_id": item["question_id"],
            "semantic_input": item.get("semantic_input") if args.judge_type == "semantic" else None,
            "support_input": item.get("support_input") if args.judge_type == "support" else None,
        })
    request_field = f"{args.judge_type}_input"
    result = {
        "schema_version": 1,
        "status": f"{args.judge_type}_only_uniform_1024_rejudge",
        "split": "development_calibration",
        "case_count": len(cases),
        "judge_type": args.judge_type,
        "judge_request_count": sum(item[request_field] is not None for item in cases),
        "source_manifest_sha256": sha256_file(args.source),
        "judge_inputs_changed": False,
        "cases": cases,
    }
    write_json(args.output, result)
    print(json.dumps({key: result[key] for key in (
        "status", "case_count", "judge_type", "judge_request_count",
        "source_manifest_sha256", "judge_inputs_changed"
    )}, indent=2))


if __name__ == "__main__":
    main()
