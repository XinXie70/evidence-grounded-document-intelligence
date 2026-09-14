"""Freeze a protocol-compliant V1 threshold on development calibration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .io import sha256_file, write_json


ALLOWED_TARGET_COVERAGES = (1.0, 0.9, 0.8, 0.6)


def build_threshold_freeze(
    evaluation: dict[str, Any], human_agreement: dict[str, Any], *, target_coverage: float
) -> dict[str, Any]:
    if evaluation.get("split") != "development_calibration":
        raise ValueError("thresholds may be selected only on development_calibration")
    if evaluation.get("status") != "development_calibration_confidence_gate_evaluated":
        raise ValueError("calibration evaluation is not complete")
    if human_agreement.get("status") != "complete" or human_agreement.get("case_count", 0) < 50:
        raise ValueError("the required human agreement audit is incomplete")
    if target_coverage not in ALLOWED_TARGET_COVERAGES:
        raise ValueError("target coverage must be one of the predeclared operating points")
    risk_coverage = evaluation.get("risk_coverage", {})
    points = risk_coverage.get("operating_points", {})
    point = points.get(str(target_coverage))
    if not isinstance(point, dict) or point.get("confidence_threshold") is None:
        raise ValueError("selected operating point is unavailable")
    maximum_coverage = risk_coverage.get("maximum_coverage")
    if isinstance(maximum_coverage, bool) or not isinstance(maximum_coverage, (int, float)):
        raise ValueError("calibration evaluation is missing maximum coverage")
    return {
        "schema_version": 1,
        "status": "protocol_corrected_and_frozen_before_locked_test",
        "split_used_for_threshold_selection": "development_calibration",
        "locked_test_accessed": False,
        "decision_rule": "answer only if policy_eligible is true and confidence >= threshold; otherwise abstain",
        "confidence_threshold": point["confidence_threshold"],
        "selected_target_coverage": target_coverage,
        "observed_calibration_operating_point": point,
        "selection_rule": "use the predeclared total-question coverage operating point; do not substitute answer retention for coverage",
        "diagnostic": {
            "all_predeclared_total_coverage_points": points,
            "maximum_attainable_coverage": float(maximum_coverage),
            "requested_target_attainable": float(maximum_coverage) >= target_coverage,
            "confidence_ordering_conclusion": "weak; calibration did not justify additional confidence-based rejection beyond the frozen eligibility gate",
            "claim_boundary": "report the confidence ordering as a weak calibration result, not as calibrated probability or monotonic risk reduction",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation", required=True, type=Path)
    parser.add_argument("--human-agreement", required=True, type=Path)
    parser.add_argument("--confidence-policy", required=True, type=Path)
    parser.add_argument("--target-coverage", required=True, type=float)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable output: {args.output}")
    result = build_threshold_freeze(
        json.loads(args.evaluation.read_text(encoding="utf-8")),
        json.loads(args.human_agreement.read_text(encoding="utf-8")),
        target_coverage=args.target_coverage,
    )
    result["artifacts"] = {
        "calibration_evaluation_sha256": sha256_file(args.evaluation),
        "human_agreement_sha256": sha256_file(args.human_agreement),
        "confidence_policy_sha256": sha256_file(args.confidence_policy),
    }
    write_json(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
