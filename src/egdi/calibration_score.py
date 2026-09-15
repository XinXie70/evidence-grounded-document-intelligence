"""Join frozen calibration labels with official judge results deterministically."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .access import require_evaluation_split_access
from .io import sha256_file, write_json
from .scoring import scoring_eligibility


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _judge_value(
    case: dict[str, Any], *, kind: str, result_dir: Path
) -> tuple[bool, dict[str, Any]]:
    spec = case.get(kind)
    if not isinstance(spec, dict) or spec.get("mode") not in {"local", "judge"}:
        raise ValueError(f"invalid {kind} specification")
    if spec["mode"] == "local":
        field = "task_correct" if kind == "semantic" else "evidence_supported"
        value = spec.get(field)
        if not isinstance(value, bool):
            raise ValueError(f"local {kind} result must define {field}")
        return value, {"mode": "local", "rule": spec.get("rule")}

    source = case.get(f"{kind}_input")
    if not isinstance(source, dict) or not isinstance(source.get("sha256"), str):
        raise ValueError(f"judge {kind} input metadata is missing")
    path = result_dir / case["pilot_id"] / f"{kind}.json"
    result = _load(path)
    if result.get("question_id") != case.get("question_id") or result.get("judge_type") != kind:
        raise ValueError(f"{kind} judge identity drift: {path}")
    if result.get("input_sha256") != source["sha256"]:
        raise ValueError(f"{kind} judge input hash drift: {path}")
    judgment = result.get("judgment")
    field = "consistent" if kind == "semantic" else "supported"
    if not isinstance(judgment, dict) or not isinstance(judgment.get(field), bool):
        raise ValueError(f"{kind} judge result is incomplete: {path}")
    return judgment[field], {
        "mode": "judge_v1",
        "result_path": str(path),
        "result_sha256": sha256_file(path),
        "response_id": result.get("response_id"),
        "reason": judgment.get("reason"),
    }


def _page_diagnostics(case: dict[str, Any]) -> dict[str, Any]:
    eligibility_record = {
        "id": case.get("question_id"),
        "answer": {"is_answerable": case.get("gold_is_answerable")},
        "evidences": [{"page": page} for page in case.get("gold_pages", [])],
    }
    eligible, exclusion_reason = scoring_eligibility(eligibility_record)
    if not eligible:
        return {
            "retrieval_scoring_eligible": False,
            "retrieval_exclusion_reason": exclusion_reason,
            "page_precision": None,
            "page_recall": None,
            "page_f1": None,
            "any_evidence_recall": None,
            "complete_evidence_recall": None,
        }
    gold = set(case.get("gold_pages", []))
    cited = set(case.get("prediction", {}).get("cited_pages", []))
    overlap = len(gold & cited)
    precision = overlap / len(cited) if cited else 0.0
    recall = overlap / len(gold)
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return {
        "retrieval_scoring_eligible": True,
        "retrieval_exclusion_reason": None,
        "page_precision": precision,
        "page_recall": recall,
        "page_f1": f1,
        "any_evidence_recall": overlap > 0,
        "complete_evidence_recall": gold <= cited,
    }


def build_calibration_audit(
    manifest: dict[str, Any], *, semantic_dir: Path, support_dir: Path
) -> dict[str, Any]:
    split = manifest.get("split", "development_calibration")
    if split not in {"development_calibration", "locked_test"}:
        raise ValueError("judge manifest must be development_calibration or locked_test")
    require_evaluation_split_access(split)
    if manifest.get("case_count") != len(manifest.get("cases", [])):
        raise ValueError("judge manifest case count mismatch")
    rows = []
    seen: set[str] = set()
    for case in manifest["cases"]:
        question_id = case.get("question_id")
        if not isinstance(question_id, str) or not question_id or question_id in seen:
            raise ValueError("question_id values must be non-empty and unique")
        seen.add(question_id)
        task_correct, semantic_provenance = _judge_value(
            case, kind="semantic", result_dir=semantic_dir
        )
        evidence_supported, support_provenance = _judge_value(
            case, kind="support", result_dir=support_dir
        )
        rows.append(
            {
                "pilot_id": case["pilot_id"],
                "question_id": question_id,
                "doc_id": case["doc_id"],
                "route": case["route"],
                "gold_is_answerable": case["gold_is_answerable"],
                "prediction_status": case["prediction"]["status"],
                "prediction_valid": case["prediction"].get("valid", True),
                "operational_failure": case["prediction"].get("operational_failure", False),
                "task_correct": task_correct,
                "evidence_supported": evidence_supported,
                "grounded_correct": task_correct and evidence_supported,
                "page_diagnostics": _page_diagnostics(case),
                "semantic_provenance": semantic_provenance,
                "support_provenance": support_provenance,
            }
        )
    answerable = [row for row in rows if row["gold_is_answerable"]]
    retrieval = [
        row["page_diagnostics"]
        for row in rows
        if row["page_diagnostics"]["retrieval_scoring_eligible"]
    ]
    if not retrieval:
        raise ValueError("evaluation contains no retrieval-scoring-eligible questions")
    return {
        "schema_version": 1,
        "status": (
            "development_calibration_automatic_judging_complete_pending_human_audit"
            if split == "development_calibration"
            else "locked_test_automatic_judging_complete"
        ),
        "split": split,
        "case_count": len(rows),
        "task_correct_count": sum(row["task_correct"] for row in rows),
        "evidence_supported_count": sum(row["evidence_supported"] for row in rows),
        "grounded_correct_count": sum(row["grounded_correct"] for row in rows),
        "answered_count": sum(row["prediction_status"] == "answerable" for row in rows),
        "abstained_count": sum(row["prediction_status"] == "insufficient_evidence" for row in rows),
        "invalid_prediction_count": sum(not row["prediction_valid"] for row in rows),
        "operational_failure_count": sum(row["operational_failure"] for row in rows),
        "answerable_count": len(answerable),
        "unanswerable_count": len(rows) - len(answerable),
        "retrieval_scoring_eligible_count": len(retrieval),
        "retrieval_exclusion_counts": {
            reason: sum(
                row["page_diagnostics"]["retrieval_exclusion_reason"] == reason
                for row in rows
            )
            for reason in ("unanswerable", "answerable_zero_evidence_anomaly", "missing_gold_evidence")
        },
        "retrieval_diagnostics_answerable_only": {
            "any_evidence_recall": sum(row["any_evidence_recall"] for row in retrieval) / len(retrieval),
            "complete_evidence_recall": sum(row["complete_evidence_recall"] for row in retrieval) / len(retrieval),
            "mean_page_precision": sum(row["page_precision"] for row in retrieval) / len(retrieval),
            "mean_page_recall": sum(row["page_recall"] for row in retrieval) / len(retrieval),
            "mean_page_f1": sum(row["page_f1"] for row in retrieval) / len(retrieval),
        },
        "cases": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--semantic-dir", required=True, type=Path)
    parser.add_argument("--support-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable output: {args.output}")
    result = build_calibration_audit(
        _load(args.manifest), semantic_dir=args.semantic_dir, support_dir=args.support_dir
    )
    result["artifacts"] = {
        "judge_manifest_sha256": sha256_file(args.manifest),
    }
    write_json(args.output, result)
    print(json.dumps({key: result[key] for key in (
        "status", "case_count", "task_correct_count", "evidence_supported_count",
        "grounded_correct_count", "answered_count", "abstained_count",
        "retrieval_diagnostics_answerable_only",
    )}, indent=2))


if __name__ == "__main__":
    main()
