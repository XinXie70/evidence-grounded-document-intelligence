"""Audit comparison-question coverage on development_tune only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any, Sequence

from .io import sha256_file, write_json


PATTERNS = {
    "strict_more_than": re.compile(r"\bmore\b.*\bthan\b", re.IGNORECASE),
    "strict_less_than": re.compile(r"\bless\b.*\bthan\b", re.IGNORECASE),
    "directional_compared_to": re.compile(
        r"\b(?:more|higher|larger|less|lower|fewer)\b.*\bcompared to\b",
        re.IGNORECASE,
    ),
    "difference_wording": re.compile(
        r"\bdifference\b|\bdiffer(?:ed|s)?\b", re.IGNORECASE
    ),
}


def audit_comparison_scope(
    benchmark: Sequence[dict[str, Any]], split_manifest: dict[str, Any]
) -> dict[str, Any]:
    """Classify answerable tune questions without inspecting other split content."""
    tune = split_manifest.get("development_tune")
    if not isinstance(tune, dict) or not isinstance(tune.get("question_ids"), list):
        raise ValueError("split manifest must contain development_tune question_ids")
    tune_ids = tune["question_ids"]
    if len(tune_ids) != len(set(tune_ids)):
        raise ValueError("development_tune question ids must be unique")
    by_id = {record.get("id"): record for record in benchmark if record.get("id") in set(tune_ids)}
    if set(by_id) != set(tune_ids):
        raise ValueError("benchmark does not contain every development_tune question")
    answerable = [
        by_id[question_id]
        for question_id in tune_ids
        if by_id[question_id].get("answer", {}).get("is_answerable") is True
    ]

    categories = {}
    union_ids: set[str] = set()
    for name, pattern in PATTERNS.items():
        matches = [
            {"question_id": record["id"], "question": record["question"]}
            for record in answerable
            if pattern.search(record["question"])
        ]
        categories[name] = {"count": len(matches), "questions": matches}
        union_ids.update(item["question_id"] for item in matches)

    denominator = len(answerable)
    current_count = categories["strict_more_than"]["count"]
    directional_count = len(
        {
            item["question_id"]
            for name in (
                "strict_more_than",
                "strict_less_than",
                "directional_compared_to",
            )
            for item in categories[name]["questions"]
        }
    )
    return {
        "schema_version": 1,
        "split": "development_tune",
        "development_tune_question_count": len(tune_ids),
        "answerable_question_count": denominator,
        "categories": categories,
        "coverage": {
            "current_strict_checker_count": current_count,
            "current_strict_checker_fraction": current_count / denominator,
            "safe_directional_extension_candidate_count": directional_count,
            "safe_directional_extension_candidate_fraction": directional_count / denominator,
            "all_comparison_wording_union_count": len(union_ids),
            "all_comparison_wording_union_fraction": len(union_ids) / denominator,
        },
        "decision": (
            "Do not present the strict more-than checker as general reliability coverage. "
            "Retain it as a failure-driven diagnostic; next test a bounded directional "
            "wording extension before considering absolute-difference questions."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--split-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable audit: {args.output}")
    benchmark = json.loads(args.benchmark.read_text(encoding="utf-8"))
    manifest = json.loads(args.split_manifest.read_text(encoding="utf-8"))
    result = audit_comparison_scope(benchmark, manifest)
    result["benchmark_sha256"] = sha256_file(args.benchmark)
    result["split_manifest_sha256"] = sha256_file(args.split_manifest)
    result["paid_api_used"] = False
    write_json(args.output, result)
    print(json.dumps(result["coverage"], indent=2))


if __name__ == "__main__":
    main()
