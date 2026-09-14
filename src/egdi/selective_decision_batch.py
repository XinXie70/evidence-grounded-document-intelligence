"""Apply the frozen V1 selective decision to a complete label-free prediction batch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .access import require_evaluation_split_access
from .io import sha256_file, write_json
from .selective_decision import apply_selective_decision


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def apply_selective_batch(
    feature_manifest: dict[str, Any],
    policy: dict[str, Any],
    threshold: dict[str, Any],
    *,
    output_dir: Path,
) -> dict[str, Any]:
    split = feature_manifest.get("split")
    require_evaluation_split_access(split)
    if feature_manifest.get("contains_gold_or_answer_labels") is not False:
        raise ValueError("feature manifest must explicitly exclude benchmark labels")
    cases = feature_manifest.get("cases")
    if not isinstance(cases, list) or len(cases) != feature_manifest.get("case_count"):
        raise ValueError("feature manifest case count mismatch")

    output_cases = []
    actions = {"retain_answer": 0, "abstain": 0}
    seen: set[str] = set()
    for case in cases:
        question_id = case.get("question_id")
        pilot_id = case.get("pilot_id")
        metadata = case.get("reasoning_result")
        features = case.get("features")
        if not isinstance(question_id, str) or question_id in seen:
            raise ValueError("question IDs must be present and unique")
        seen.add(question_id)
        if not isinstance(pilot_id, str) or not pilot_id:
            raise ValueError("pilot_id must be a non-empty string")
        if not isinstance(metadata, dict) or not isinstance(metadata.get("path"), str):
            raise ValueError("reasoning result metadata is invalid")
        if not isinstance(features, dict):
            raise ValueError("confidence features are missing")
        source_path = Path(metadata["path"])
        if sha256_file(source_path) != metadata.get("sha256"):
            raise ValueError(f"reasoning result checksum mismatch: {source_path}")
        source = _load(source_path)
        final = apply_selective_decision(source, features, policy, threshold)
        target = output_dir / pilot_id / "real_retrieval.json"
        if target.exists():
            raise FileExistsError(f"refusing to overwrite final prediction: {target}")
        final["selective_decision"]["source_result_sha256"] = metadata["sha256"]
        write_json(target, final)
        action = final["selective_decision"]["action"]
        actions[action] += 1
        output_cases.append({
            "pilot_id": pilot_id,
            "question_id": question_id,
            "doc_id": case.get("doc_id"),
            "action": action,
            "final_prediction": {"path": str(target), "sha256": sha256_file(target)},
        })
    return {
        "schema_version": 1,
        "status": "selective_predictions_frozen_before_label_access",
        "split": split,
        "contains_gold_or_answer_labels": False,
        "case_count": len(output_cases),
        "retained_answer_count": actions["retain_answer"],
        "abstained_count": actions["abstain"],
        "cases": output_cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--threshold", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    manifest_path = args.output_dir / "manifest.json"
    if manifest_path.exists():
        raise FileExistsError(f"refusing to overwrite final manifest: {manifest_path}")
    result = apply_selective_batch(
        _load(args.features),
        _load(args.policy),
        _load(args.threshold),
        output_dir=args.output_dir,
    )
    result["input_sha256"] = {
        "features": sha256_file(args.features),
        "policy": sha256_file(args.policy),
        "threshold": sha256_file(args.threshold),
    }
    write_json(manifest_path, result)
    print(json.dumps({key: result[key] for key in (
        "status", "split", "case_count", "retained_answer_count", "abstained_count"
    )}, indent=2))


if __name__ == "__main__":
    main()
