"""Apply the frozen label-free confidence decision to one reasoning result."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from .confidence_policy_v1 import score_features
from .io import sha256_file, write_json
from .reasoning_api import validate_grounded_output


THRESHOLD_STATUSES = {
    "frozen_on_development_calibration_before_locked_test",
    "protocol_corrected_and_frozen_before_locked_test",
}


def _validate_threshold(config: dict[str, Any]) -> float:
    if config.get("status") not in THRESHOLD_STATUSES:
        raise ValueError("confidence threshold is not frozen")
    if config.get("split_used_for_threshold_selection") != "development_calibration":
        raise ValueError("confidence threshold was not selected on development_calibration")
    if config.get("locked_test_accessed") is not False:
        raise ValueError("threshold artifact must predate locked-test access")
    threshold = config.get("confidence_threshold")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise ValueError("confidence threshold must be numeric")
    threshold = float(threshold)
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise ValueError("confidence threshold must be finite and in [0, 1]")
    return threshold


def _expected_policy_eligibility(result: dict[str, Any]) -> bool:
    output = result.get("output")
    validation = result.get("validation")
    if not isinstance(output, dict) or not isinstance(validation, dict):
        raise ValueError("reasoning result requires output and validation objects")
    citations = output.get("cited_pages")
    if not isinstance(citations, list):
        raise ValueError("reasoning output cited_pages must be a list")
    return (
        output.get("status") == "answerable"
        and validation.get("valid") is True
        and validation.get("citations_within_supplied_context") is True
        and bool(citations)
    )


def apply_selective_decision(
    reasoning_result: dict[str, Any],
    features: dict[str, Any],
    policy: dict[str, Any],
    threshold_config: dict[str, Any],
) -> dict[str, Any]:
    """Return a final answer or deterministic abstention without evaluation labels."""
    question_id = reasoning_result.get("question_id")
    if not isinstance(question_id, str) or not question_id:
        raise ValueError("reasoning result requires a question_id")
    if features.get("question_id") != question_id:
        raise ValueError("reasoning result and confidence features do not match")
    if features.get("policy_eligible") is not _expected_policy_eligibility(reasoning_result):
        raise ValueError("policy eligibility does not match the reasoning result")

    threshold = _validate_threshold(threshold_config)
    confidence = score_features(features, policy)
    eligible = features["policy_eligible"]
    retained = eligible and confidence >= threshold

    final = dict(reasoning_result)
    if retained:
        action = "retain_answer"
        reason = "eligible_and_at_or_above_threshold"
    else:
        action = "abstain"
        reason = "ineligible" if not eligible else "below_confidence_threshold"
        final["output"] = {
            "answer": None,
            "cited_pages": [],
            "status": "insufficient_evidence",
        }
        final["validation"] = validate_grounded_output(
            final["output"], final.get("evidence_pages", [])
        )
    final["selective_decision"] = {
        "action": action,
        "reason": reason,
        "policy_eligible": eligible,
        "confidence": confidence,
        "confidence_threshold": threshold,
        "comparison": "confidence >= threshold",
    }
    return final


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--features", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--threshold", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable output: {args.output}")
    final = apply_selective_decision(
        _load_object(args.result),
        _load_object(args.features),
        _load_object(args.policy),
        _load_object(args.threshold),
    )
    final["selective_decision"]["artifact_sha256"] = {
        "source_result": sha256_file(args.result),
        "features": sha256_file(args.features),
        "policy": sha256_file(args.policy),
        "threshold": sha256_file(args.threshold),
    }
    write_json(args.output, final)
    print(json.dumps(final, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
