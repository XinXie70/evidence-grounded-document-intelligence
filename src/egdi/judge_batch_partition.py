"""Partition semantic/support judge requests into independently capped batches."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .calibration_judge_batch import build_plan
from .io import sha256_file, write_json
from .reasoning_api import validate_pricing_snapshot


def partition_judge_requests(
    plan: list[dict[str, Any]], *, target_usd: float
) -> list[list[dict[str, Any]]]:
    if (
        isinstance(target_usd, bool)
        or not isinstance(target_usd, (int, float))
        or target_usd <= 0
    ):
        raise ValueError("target_usd must be positive")
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    running = 0.0
    for request in plan:
        cost = request.get("conservative_cost_usd")
        if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost < 0:
            raise ValueError("every judge request requires a non-negative cost")
        if cost > target_usd:
            raise ValueError(
                f"single judge request exceeds partition target: "
                f"{request.get('pilot_id')}/{request.get('judge_type')}"
            )
        if current and running + cost > target_usd:
            batches.append(current)
            current = []
            running = 0.0
        current.append(request)
        running += cost
    if current:
        batches.append(current)
    return batches


def build_batch_manifest(
    parent: dict[str, Any], requests: list[dict[str, Any]], *, parent_sha256: str, batch_id: str
) -> dict[str, Any]:
    case_by_key = {
        (case["pilot_id"], judge_type): (case, case[f"{judge_type}_input"])
        for case in parent.get("cases", [])
        for judge_type in ("semantic", "support")
        if case.get(f"{judge_type}_input") is not None
    }
    cases = []
    for request in requests:
        key = (request["pilot_id"], request["judge_type"])
        if key not in case_by_key:
            raise ValueError(f"judge request is not present in parent manifest: {key}")
        source, metadata = case_by_key[key]
        judge_type = request["judge_type"]
        cases.append({
            "pilot_id": source["pilot_id"],
            "question_id": source["question_id"],
            "doc_id": source["doc_id"],
            f"{judge_type}_input": metadata,
        })
    return {
        "schema_version": 1,
        "status": "judge_batch_partition_frozen_before_execution",
        "split": parent["split"],
        "parent_manifest_sha256": parent_sha256,
        "batch_id": batch_id,
        "case_count": len(cases),
        "judge_request_count": len(requests),
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--semantic-config", required=True, type=Path)
    parser.add_argument("--support-config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--target-usd", type=float, default=0.95)
    parser.add_argument("--hard-cap-usd", type=float, default=1.0)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError(f"refusing to overwrite immutable output: {args.output_dir}")
    if args.target_usd > args.hard_cap_usd:
        raise ValueError("partition target must not exceed hard cap")

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    configs = {
        "semantic": (
            args.semantic_config,
            json.loads(args.semantic_config.read_text(encoding="utf-8")),
        ),
        "support": (
            args.support_config,
            json.loads(args.support_config.read_text(encoding="utf-8")),
        ),
    }
    semantic = configs["semantic"][1]
    pricing_path = args.semantic_config.parent / semantic["pricing_snapshot_path"]
    pricing = validate_pricing_snapshot(
        json.loads(pricing_path.read_text(encoding="utf-8")),
        expected_model=semantic["model"],
    )
    plan = build_plan(manifest, configs, pricing)
    batches = partition_judge_requests(plan, target_usd=args.target_usd)
    parent_sha256 = sha256_file(args.manifest)
    summaries = []
    for index, requests in enumerate(batches, start=1):
        batch_id = f"batch_{index:02d}"
        batch_manifest = build_batch_manifest(
            manifest, requests, parent_sha256=parent_sha256, batch_id=batch_id
        )
        manifest_path = args.output_dir / f"{batch_id}_manifest.json"
        write_json(manifest_path, batch_manifest)
        conservative_cost = round(
            sum(item["conservative_cost_usd"] for item in requests), 9
        )
        budget = {
            "schema_version": 1,
            "status": "proposed_not_started",
            "scope": f"{batch_id} of frozen {manifest['split']} V1 judge evaluation",
            "currency": "USD",
            "judge_request_count": len(requests),
            "semantic_request_count": sum(
                item["judge_type"] == "semantic" for item in requests
            ),
            "support_request_count": sum(
                item["judge_type"] == "support" for item in requests
            ),
            "conservative_cost_estimate_usd": conservative_cost,
            "approved_hard_cap_usd": args.hard_cap_usd,
            "input_manifest_sha256": sha256_file(manifest_path),
            "semantic_config_sha256": sha256_file(args.semantic_config),
            "support_config_sha256": sha256_file(args.support_config),
            "paid_request_sent": False,
            "approval_required_before_execution": True,
        }
        budget_path = args.output_dir / f"{batch_id}_budget.json"
        write_json(budget_path, budget)
        summaries.append({
            "batch_id": batch_id,
            "judge_request_count": len(requests),
            "conservative_cost_estimate_usd": conservative_cost,
            "manifest": str(manifest_path),
            "budget": str(budget_path),
        })
    print(json.dumps({"batch_count": len(summaries), "batches": summaries}, indent=2))


if __name__ == "__main__":
    main()
