"""Frozen tune-only V1 confidence formula and deterministic evaluation join."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from .confidence_features_v1 import ROUTES, contains_forbidden_confidence_key
from .selective_evaluation import evaluate_risk_coverage


SCORE_FIELDS = (
    "query_token_coverage_ratio",
    "citation_to_evidence_ratio",
    "bm25_dense_agreement_at_10",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _unit_interval(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ValueError(f"{field} must be finite and in [0, 1]")
    return result


def validate_policy(policy: dict[str, Any]) -> None:
    weights = policy.get("weights")
    priors = policy.get("route_priors")
    missing = policy.get("missing_values")
    if not isinstance(weights, dict) or set(weights) != {"route_prior", *SCORE_FIELDS}:
        raise ValueError("policy weights do not match the frozen formula")
    parsed_weights = {key: _unit_interval(value, f"weight {key}") for key, value in weights.items()}
    if not math.isclose(sum(parsed_weights.values()), 1.0, abs_tol=1e-12):
        raise ValueError("policy weights must sum to one")
    if not isinstance(priors, dict) or set(priors) != ROUTES:
        raise ValueError("route_priors must define every frozen route")
    for route, value in priors.items():
        _unit_interval(value, f"route prior {route}")
    if not isinstance(missing, dict) or set(missing) != {"bm25_dense_agreement_at_10"}:
        raise ValueError("only the frozen dense-agreement missing rule is supported")
    _unit_interval(missing["bm25_dense_agreement_at_10"], "dense-agreement missing value")


def score_features(features: dict[str, Any], policy: dict[str, Any]) -> float:
    """Return the scalar V1 confidence using inference-time fields only."""
    validate_policy(policy)
    if contains_forbidden_confidence_key(features):
        raise ValueError("confidence features contain forbidden evaluation fields")
    route = features.get("route")
    if route not in ROUTES:
        raise ValueError("feature route is not part of the frozen policy")
    weights = policy["weights"]
    agreement = features.get("bm25_dense_agreement_at_10")
    if agreement is None:
        agreement = policy["missing_values"]["bm25_dense_agreement_at_10"]
    values = {
        "route_prior": policy["route_priors"][route],
        "query_token_coverage_ratio": features.get("query_token_coverage_ratio"),
        "citation_to_evidence_ratio": features.get("citation_to_evidence_ratio"),
        "bm25_dense_agreement_at_10": agreement,
    }
    return sum(
        _unit_interval(value, field) * float(weights[field])
        for field, value in values.items()
    )


def evaluate_artifacts(
    features_artifact: dict[str, Any],
    audit_artifact: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    """Join frozen predictions with tune labels and evaluate deterministic confidence ordering."""
    validate_policy(policy)
    if features_artifact.get("contains_gold_or_answer_labels") is not False:
        raise ValueError("feature artifact must explicitly exclude evaluation labels")
    split = features_artifact.get("split")
    if split not in {"development_tune", "development_calibration"}:
        raise ValueError("feature artifact split must be development_tune or development_calibration")
    audit_split = audit_artifact.get("split", split)
    if audit_split != split:
        raise ValueError("feature and audit artifact splits must match")
    feature_cases = features_artifact.get("cases")
    audit_cases = audit_artifact.get("cases")
    if not isinstance(feature_cases, list) or not isinstance(audit_cases, list):
        raise ValueError("features and audit artifacts require case lists")
    labels = {item.get("question_id"): item for item in audit_cases if isinstance(item, dict)}
    if len(labels) != len(audit_cases):
        raise ValueError("audit question_id values must be present and unique")
    records = []
    case_rows = []
    for item in feature_cases:
        question_id = item.get("question_id")
        if question_id not in labels:
            raise ValueError(f"missing audit label for {question_id}")
        features = item.get("features")
        if not isinstance(features, dict) or features.get("question_id") != question_id:
            raise ValueError("feature case identity drift")
        audit = labels.pop(question_id)
        task_correct = audit.get("task_correct")
        grounded_correct = audit.get("grounded_correct")
        if not isinstance(task_correct, bool) or not isinstance(grounded_correct, bool):
            raise ValueError("audit labels must be boolean")
        confidence = score_features(features, policy)
        record = {
            "question_id": question_id,
            "confidence": confidence,
            "policy_eligible": features.get("policy_eligible"),
            "task_correct": task_correct,
            "grounded_correct": grounded_correct,
        }
        records.append(record)
        case_rows.append({"pilot_id": item.get("pilot_id"), **record})
    if labels:
        raise ValueError("audit contains questions absent from the feature artifact")
    risk_coverage = evaluate_risk_coverage(records)
    return {
        "schema_version": 1,
        "status": f"{split}_confidence_gate_evaluated",
        "split": split,
        "question_count": len(records),
        "task_correct_count": sum(item["task_correct"] for item in records),
        "grounded_correct_count": sum(item["grounded_correct"] for item in records),
        "policy_eligible_count": sum(item["policy_eligible"] for item in records),
        "cases": case_rows,
        "risk_coverage": risk_coverage,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", required=True, type=Path)
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = evaluate_artifacts(
        _load_json(args.features), _load_json(args.audit), _load_json(args.policy)
    )
    result["artifacts"] = {
        "features_sha256": _sha256(args.features),
        "audit_sha256": _sha256(args.audit),
        "policy_sha256": _sha256(args.policy),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "status", "question_count", "task_correct_count", "grounded_correct_count",
        "policy_eligible_count", "artifacts"
    )}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
