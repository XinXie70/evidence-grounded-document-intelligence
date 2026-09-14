"""Freeze post-generation confidence features before tune outcome scoring."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .access import require_evaluation_split_access
from .confidence_features_v1 import (
    attach_postgeneration_confidence_features,
    contains_forbidden_confidence_key,
)
from .io import sha256_file, write_json


ALLOWED_SPLITS = {"development_tune", "development_calibration", "locked_test"}


def build_confidence_feature_manifest(
    input_manifest: dict[str, Any],
    *,
    result_dir: Path,
    result_overrides: dict[str, Path] | None = None,
) -> dict[str, Any]:
    split = input_manifest.get("split")
    if split not in ALLOWED_SPLITS:
        raise ValueError("unknown evaluation split")
    require_evaluation_split_access(split)
    if input_manifest.get("contains_gold_or_answer_labels") is not False:
        raise ValueError("input manifest must explicitly exclude benchmark labels")
    cases = input_manifest.get("cases")
    if not isinstance(cases, list) or len(cases) != input_manifest.get("case_count"):
        raise ValueError("input manifest case count mismatch")
    output_cases = []
    seen: set[str] = set()
    for case in cases:
        question_id = case.get("question_id")
        pilot_id = case.get("pilot_id")
        features = case.get("confidence_features")
        if not isinstance(question_id, str) or not isinstance(pilot_id, str):
            raise ValueError("case identity is invalid")
        if question_id in seen:
            raise ValueError(f"duplicate question_id: {question_id}")
        seen.add(question_id)
        if not isinstance(features, dict) or contains_forbidden_confidence_key(features):
            raise ValueError("retrieval confidence features are invalid")
        result_path = (
            result_overrides.get(pilot_id)
            if result_overrides is not None and pilot_id in result_overrides
            else result_dir / pilot_id / "real_retrieval.json"
        )
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("question_id") != question_id or result.get("doc_id") != case.get("doc_id"):
            raise ValueError(f"reasoning result identity drift: {result_path}")
        if result.get("evidence_pages") != case.get("evidence_pages"):
            raise ValueError(f"reasoning result evidence drift: {result_path}")
        combined = attach_postgeneration_confidence_features(features, result)
        output_cases.append(
            {
                "pilot_id": pilot_id,
                "question_id": question_id,
                "doc_id": case["doc_id"],
                "route": case["route"],
                "reasoning_result": {
                    "path": str(result_path),
                    "sha256": sha256_file(result_path),
                },
                "features": combined,
            }
        )
    output = {
        "schema_version": 1,
        "status": "predictions_and_label_free_features_frozen_before_outcome_scoring",
        "split": split,
        "contains_gold_or_answer_labels": False,
        "case_count": len(output_cases),
        "cases": output_cases,
    }
    if contains_forbidden_confidence_key(output):
        raise ValueError("feature manifest contains a forbidden evaluation field")
    return output


def apply_case_corrections(
    base: dict[str, Any], correction: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Replace explicitly versioned cases while preserving identities and retrieval pages."""
    for label, manifest in (("base", base), ("correction", correction)):
        if manifest.get("contains_gold_or_answer_labels") is not False:
            raise ValueError(f"{label} manifest must explicitly exclude benchmark labels")
    corrected = {case["pilot_id"]: case for case in correction.get("cases", [])}
    if not corrected:
        raise ValueError("correction manifest contains no cases")
    output_cases = []
    used = []
    for case in base.get("cases", []):
        replacement = corrected.get(case.get("pilot_id"))
        if replacement is None:
            output_cases.append(case)
            continue
        for field in ("pilot_id", "question_id", "doc_id", "route", "evidence_pages"):
            if replacement.get(field) != case.get(field):
                raise ValueError(f"correction changed frozen case field: {field}")
        if replacement.get("confidence_features") != case.get("confidence_features"):
            raise ValueError("correction changed frozen retrieval confidence features")
        output_cases.append(replacement)
        used.append(case["pilot_id"])
    if set(used) != set(corrected):
        raise ValueError("correction contains a case absent from the base manifest")
    return {**base, "cases": output_cases}, sorted(used)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-manifest", required=True, type=Path)
    parser.add_argument("--result-dir", required=True, type=Path)
    parser.add_argument("--correction-input-manifest", type=Path)
    parser.add_argument("--correction-result-dir", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable output: {args.output}")
    source = json.loads(args.input_manifest.read_text(encoding="utf-8"))
    corrections = []
    overrides = {}
    if (args.correction_input_manifest is None) != (args.correction_result_dir is None):
        raise ValueError("correction input manifest and result directory must be supplied together")
    if args.correction_input_manifest is not None:
        correction = json.loads(args.correction_input_manifest.read_text(encoding="utf-8"))
        source, corrections = apply_case_corrections(source, correction)
        overrides = {
            pilot_id: args.correction_result_dir / pilot_id / "real_retrieval.json"
            for pilot_id in corrections
        }
    result = build_confidence_feature_manifest(
        source, result_dir=args.result_dir, result_overrides=overrides
    )
    result["input_manifest_sha256"] = sha256_file(args.input_manifest)
    if args.correction_input_manifest is not None:
        result["correction"] = {
            "input_manifest_sha256": sha256_file(args.correction_input_manifest),
            "corrected_pilot_ids": corrections,
        }
    write_json(args.output, result)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "output_sha256": sha256_file(args.output),
                "case_count": result["case_count"],
                "policy_eligible_count": sum(
                    case["features"]["policy_eligible"] for case in result["cases"]
                ),
                "contains_gold_or_answer_labels": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
