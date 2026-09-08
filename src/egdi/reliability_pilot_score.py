"""Validate a completed human audit and score each Reliability pilot condition."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .io import sha256_file, write_json
from .reliability import aggregate_selective_metrics, classify_reliability_outcome


CONDITIONS = ("closed_book", "real_retrieval", "oracle_page")


def score_completed_audit(
    audit: dict[str, Any],
    results_dir: Path,
) -> dict[str, Any]:
    """Cross-check human labels against immutable responses and aggregate metrics."""
    if audit.get("status") != "complete":
        raise ValueError("human audit is not complete")
    pilots = audit.get("pilots")
    if not isinstance(pilots, list) or len(pilots) != audit.get("completed_pilot_count"):
        raise ValueError("completed pilot count does not match audit records")
    if audit.get("pending_pilot_count") != 0:
        raise ValueError("human audit still has pending pilots")
    pilot_ids = [item.get("pilot_id") for item in pilots if isinstance(item, dict)]
    if len(pilot_ids) != len(pilots) or len(set(pilot_ids)) != len(pilot_ids):
        raise ValueError("pilot IDs must be present and unique")

    by_condition: dict[str, list[dict[str, Any]]] = {name: [] for name in CONDITIONS}
    contracts: dict[str, list[tuple[str, bool]]] = {name: [] for name in CONDITIONS}
    for pilot in pilots:
        if pilot.get("user_confirmed") is not True:
            raise ValueError(f"pilot is not user-confirmed: {pilot.get('pilot_id')}")
        condition_audits = pilot.get("conditions")
        if not isinstance(condition_audits, dict) or set(condition_audits) != set(CONDITIONS):
            raise ValueError(f"pilot conditions are incomplete: {pilot['pilot_id']}")
        for condition in CONDITIONS:
            result_path = results_dir / pilot["pilot_id"] / f"{condition}.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            reviewed = condition_audits[condition]
            if result.get("question_id") != pilot.get("question_id"):
                raise ValueError(f"result question mismatch: {result_path}")
            if result.get("condition") != condition:
                raise ValueError(f"result condition mismatch: {result_path}")
            output = result.get("output")
            if not isinstance(output, dict):
                raise ValueError(f"result output is invalid: {result_path}")
            if output.get("status") != reviewed.get("response_status"):
                raise ValueError(f"audited status differs from result: {result_path}")
            if output.get("answer") != reviewed.get("answer"):
                raise ValueError(f"audited answer differs from result: {result_path}")

            reliability_record = {
                "question_id": pilot["question_id"],
                "benchmark_is_answerable": pilot["benchmark_is_answerable"],
                "response_status": reviewed["response_status"],
                "answer": reviewed["answer"],
                "evidence_sufficient": reviewed.get("evidence_sufficient"),
            }
            if reviewed["response_status"] == "answerable":
                reliability_record["answer_correct"] = reviewed.get("answer_correct")
                reliability_record["grounded_correct"] = reviewed.get("grounded_correct")
            classified = classify_reliability_outcome(reliability_record)
            if classified["outcome"] != reviewed.get("outcome"):
                raise ValueError(f"audited outcome is inconsistent: {result_path}")
            by_condition[condition].append(reliability_record)

            validation = result.get("validation")
            contract_valid = validation.get("valid") if isinstance(validation, dict) else None
            if not isinstance(contract_valid, bool):
                raise ValueError(f"result validation is invalid: {result_path}")
            explicitly_reviewed = reviewed.get("response_contract_valid")
            if explicitly_reviewed is not None and explicitly_reviewed != contract_valid:
                raise ValueError(f"audited contract validity differs from result: {result_path}")
            contracts[condition].append((pilot["pilot_id"], contract_valid))

    output_conditions = {}
    for condition in CONDITIONS:
        metrics = aggregate_selective_metrics(by_condition[condition])
        classified = [classify_reliability_outcome(item) for item in by_condition[condition]]
        valid_by_pilot = dict(contracts[condition])
        valid_count = sum(valid_by_pilot.values())
        total = len(classified)
        task_and_contract = sum(
            item["benchmark_task_correct"] and valid_by_pilot[pilot_id]
            for item, pilot_id in zip(classified, valid_by_pilot)
        )
        contextual_and_contract = sum(
            item["contextual_reliability_correct"] and valid_by_pilot[pilot_id]
            for item, pilot_id in zip(classified, valid_by_pilot)
        )
        output_conditions[condition] = {
            "semantic_metrics": metrics,
            "response_contract": {
                "valid_count": valid_count,
                "invalid_count": total - valid_count,
                "valid_rate": valid_count / total,
                "invalid_pilot_ids": [
                    pilot_id for pilot_id, valid in contracts[condition] if not valid
                ],
            },
            "supplemental_contract_adjusted_metrics": {
                "benchmark_task_accuracy": task_and_contract / total,
                "contextual_reliability_accuracy": contextual_and_contract / total,
            },
        }
    return {
        "schema_version": 1,
        "status": "complete",
        "pilot_count": len(pilots),
        "conditions": output_conditions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable score: {args.output}")
    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    scored = score_completed_audit(audit, args.results_dir)
    scored["audit_sha256"] = sha256_file(args.audit)
    scored["results_progress_sha256"] = sha256_file(args.results_dir / "progress.json")
    write_json(args.output, scored)
    print(json.dumps(scored, indent=2))


if __name__ == "__main__":
    main()
