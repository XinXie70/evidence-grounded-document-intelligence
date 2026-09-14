"""Partition a frozen V1 reasoning manifest into independently capped batches."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .io import sha256_file, write_json
from .reasoning_api import validate_execution_logging_config, validate_pricing_snapshot
from .v1_reasoning_batch import build_v1_batch_plan


def partition_cases(
    manifest: dict[str, Any], plan: list[dict[str, Any]], *, target_usd: float
) -> list[list[dict[str, Any]]]:
    """Preserve case order while keeping each conservative paid sum below target."""
    if isinstance(target_usd, bool) or not isinstance(target_usd, (int, float)) or target_usd <= 0:
        raise ValueError("target_usd must be positive")
    costs = {item["question_id"]: item["conservative_cost_usd"] for item in plan}
    batches: list[list[dict[str, Any]]] = [[]]
    running = 0.0
    for case in manifest["cases"]:
        cost = costs.get(case["question_id"], 0.0)
        if cost > target_usd:
            raise ValueError(f"single request exceeds partition target: {case['question_id']}")
        if cost and running + cost > target_usd and batches[-1]:
            batches.append([])
            running = 0.0
        batches[-1].append(case)
        running += cost
    return [batch for batch in batches if batch]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--target-usd", type=float, default=0.95)
    parser.add_argument("--hard-cap-usd", type=float, default=1.0)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError(f"refusing to overwrite immutable output: {args.output_dir}")
    if args.target_usd > args.hard_cap_usd:
        raise ValueError("partition target must not exceed hard cap")

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    config = validate_execution_logging_config(
        json.loads(args.config.read_text(encoding="utf-8"))
    )
    pricing_path = args.config.parent / config["pricing_snapshot_path"]
    pricing = validate_pricing_snapshot(
        json.loads(pricing_path.read_text(encoding="utf-8")),
        expected_model=config["model"],
    )
    plan = build_v1_batch_plan(manifest, config, pricing)
    plan_by_id = {item["question_id"]: item for item in plan}
    batches = partition_cases(manifest, plan, target_usd=args.target_usd)
    summary = []
    for index, cases in enumerate(batches, start=1):
        batch_id = f"batch_{index:02d}"
        batch_manifest = {
            **{key: value for key, value in manifest.items() if key not in {"cases", "case_count", "paid_request_count"}},
            "status": "calibration_partition_frozen_before_reasoning",
            "parent_manifest_sha256": sha256_file(args.manifest),
            "batch_id": batch_id,
            "case_count": len(cases),
            "paid_request_count": sum(case["question_id"] in plan_by_id for case in cases),
            "cases": cases,
        }
        manifest_path = args.output_dir / f"{batch_id}_manifest.json"
        write_json(manifest_path, batch_manifest)
        batch_cost = round(
            sum(plan_by_id[case["question_id"]]["conservative_cost_usd"] for case in cases if case["question_id"] in plan_by_id),
            9,
        )
        budget = {
            "schema_version": 1,
            "status": "proposed_not_started",
            "scope": f"{batch_id} of frozen development_calibration V1 reasoning",
            "currency": "USD",
            "unique_paid_request_count": batch_manifest["paid_request_count"],
            "local_policy_abstention_count": len(cases) - batch_manifest["paid_request_count"],
            "model": config["model"],
            "reasoning_effort": config["reasoning_effort"],
            "maximum_output_tokens_per_call": config["max_output_tokens"],
            "conservative_cost_estimate_usd": batch_cost,
            "approved_hard_cap_usd": args.hard_cap_usd,
            "input_manifest_sha256": sha256_file(manifest_path),
            "config_sha256": sha256_file(args.config),
            "paid_request_sent": False,
            "approval_required_before_execution": True,
        }
        budget_path = args.output_dir / f"{batch_id}_budget.json"
        write_json(budget_path, budget)
        summary.append(
            {
                "batch_id": batch_id,
                "case_count": len(cases),
                "paid_request_count": batch_manifest["paid_request_count"],
                "local_abstention_count": budget["local_policy_abstention_count"],
                "conservative_cost_estimate_usd": batch_cost,
                "manifest": str(manifest_path),
                "budget": str(budget_path),
            }
        )
    print(json.dumps({"batch_count": len(summary), "batches": summary}, indent=2))


if __name__ == "__main__":
    main()
