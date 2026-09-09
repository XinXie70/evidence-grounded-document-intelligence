"""Run a checksum-pinned batch of generic comparison fact-extraction requests."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .io import canonical_json_bytes, sha256_file, write_json
from .reasoning_api import (
    COST_ACKNOWLEDGEMENT,
    build_openai_request,
    validate_execution_logging_config,
    validate_pricing_snapshot,
    validate_comparison_fact_output,
)


def build_batch_plan(
    manifest: dict[str, Any],
    config: dict[str, Any],
    pricing: dict[str, Any],
) -> list[dict[str, Any]]:
    """Validate every frozen input and conservatively price each request."""
    cases = manifest.get("cases")
    if not isinstance(cases, list) or len(cases) != manifest.get("case_count"):
        raise ValueError("manifest case count does not match cases")

    plan: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for case in cases:
        case_id = case.get("case_id")
        input_path_value = case.get("input_path")
        if not isinstance(case_id, str) or not case_id or case_id in seen_ids:
            raise ValueError("case_id must be non-empty and unique")
        if not isinstance(input_path_value, str):
            raise ValueError(f"missing input path: {case_id}")
        seen_ids.add(case_id)

        input_path = Path(input_path_value)
        input_sha256 = sha256_file(input_path)
        if input_sha256 != case.get("input_sha256"):
            raise ValueError(f"input checksum mismatch: {input_path}")
        record = json.loads(input_path.read_text(encoding="utf-8"))
        if record.get("question_id") != case.get("question_id"):
            raise ValueError(f"question id mismatch: {input_path}")
        if record.get("condition") != "real_retrieval_fact_extraction":
            raise ValueError(f"unexpected condition: {input_path}")

        request = build_openai_request(record, config, input_base_dir=input_path.parent)
        request_bytes = canonical_json_bytes(request)
        estimated_input_tokens = math.ceil(len(request_bytes.decode("utf-8")) / 3)
        conservative_cost = (
            estimated_input_tokens
            * pricing["input_usd_per_million"]
            * pricing["cache_write_input_multiplier"]
            + config["max_output_tokens"] * pricing["output_usd_per_million"]
        ) / 1_000_000
        plan.append({
            "case_id": case_id,
            "question_id": case["question_id"],
            "input_path": str(input_path),
            "input_sha256": input_sha256,
            "request_sha256": hashlib.sha256(request_bytes).hexdigest(),
            "conservative_input_tokens": estimated_input_tokens,
            "conservative_cost_usd": round(conservative_cost, 9),
        })
    return plan


def _load_valid_result(
    path: Path,
    item: dict[str, Any],
    *,
    config_sha256: str,
) -> dict[str, Any] | None:
    if not path.exists():
        return None
    result = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "question_id": item["question_id"],
        "condition": "real_retrieval_fact_extraction",
        "input_sha256": item["input_sha256"],
        "config_sha256": config_sha256,
        "request_sha256": item["request_sha256"],
    }
    for key, value in expected.items():
        if result.get(key) != value:
            raise ValueError(f"existing result {key} mismatch: {path}")
    if result.get("call_log", {}).get("status") != "ok":
        raise ValueError(f"existing result is not successful: {path}")
    current_validation = validate_comparison_fact_output(
        result.get("output", {}), result.get("evidence_pages", [])
    )
    if not current_validation["valid"]:
        raise ValueError(f"existing result failed validation: {path}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--budget", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--acknowledge-cost")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    config = validate_execution_logging_config(
        json.loads(args.config.read_text(encoding="utf-8"))
    )
    if config.get("output_role") != "comparison_fact_extraction":
        raise ValueError("config output_role must be comparison_fact_extraction")
    pricing_path = args.config.parent / config["pricing_snapshot_path"]
    pricing = validate_pricing_snapshot(
        json.loads(pricing_path.read_text(encoding="utf-8")),
        expected_model=config["model"],
    )
    budget = json.loads(args.budget.read_text(encoding="utf-8"))
    config_sha256 = sha256_file(args.config)
    if budget.get("config_sha256") != config_sha256:
        raise ValueError("budget/config checksum mismatch")
    if budget.get("input_manifest_sha256") != sha256_file(args.manifest):
        raise ValueError("budget/input-manifest checksum mismatch")
    cap = budget.get("approved_hard_cap_usd")
    if budget.get("status") != "approved_not_started" or not isinstance(cap, (int, float)):
        raise ValueError("budget is not explicitly approved")

    plan = build_batch_plan(manifest, config, pricing)
    conservative_total = round(sum(item["conservative_cost_usd"] for item in plan), 9)
    if len(plan) != budget.get("unique_paid_request_count"):
        raise ValueError("request count differs from approved budget")
    if conservative_total > cap:
        raise RuntimeError("conservative batch estimate exceeds approved hard cap")

    summary = {
        "mode": "execute" if args.execute else "dry_run",
        "paid_request_sent": False,
        "case_count": len(plan),
        "conservative_cost_estimate_usd": conservative_total,
        "approved_hard_cap_usd": cap,
        "output_dir": str(args.output_dir),
        "cases": [
            {
                "case_id": item["case_id"],
                "conservative_input_tokens": item["conservative_input_tokens"],
                "conservative_cost_usd": item["conservative_cost_usd"],
            }
            for item in plan
        ],
    }
    if not args.execute:
        print(json.dumps(summary, indent=2))
        return
    if args.acknowledge_cost != COST_ACKNOWLEDGEMENT:
        raise RuntimeError("paid execution requires the exact cost acknowledgement")
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not configured")

    actual_cost = 0.0
    completed_count = 0
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for index, item in enumerate(plan, start=1):
        result_path = args.output_dir / item["case_id"] / "result.json"
        result = _load_valid_result(result_path, item, config_sha256=config_sha256)
        if result is None:
            if actual_cost + item["conservative_cost_usd"] > cap:
                raise RuntimeError("stopped before next request to preserve approved cap")
            result_path.parent.mkdir(parents=True, exist_ok=True)
            command = [
                sys.executable,
                "-m",
                "egdi.reasoning_api",
                "--input",
                item["input_path"],
                "--config",
                str(args.config),
                "--output",
                str(result_path),
                "--execute",
                "--acknowledge-cost",
                COST_ACKNOWLEDGEMENT,
            ]
            completed = subprocess.run(command, text=True, capture_output=True)
            if completed.returncode != 0:
                if completed.stderr:
                    print(completed.stderr, file=sys.stderr)
                raise RuntimeError(f"paid request failed at {item['case_id']}")
            result = _load_valid_result(result_path, item, config_sha256=config_sha256)
            if result is None:
                raise RuntimeError("paid request returned without a result file")

        paid_cost = result["call_log"].get("estimated_cost")
        if isinstance(paid_cost, bool) or not isinstance(paid_cost, (int, float)):
            raise ValueError("result paid cost is invalid")
        actual_cost += paid_cost
        if actual_cost > cap:
            raise RuntimeError("actual logged cost exceeded approved cap")
        completed_count += 1
        progress = {
            **summary,
            "mode": "execute",
            "paid_request_sent": True,
            "completed_cases": completed_count,
            "actual_cost_usd": round(actual_cost, 9),
            "remaining_cap_usd": round(cap - actual_cost, 9),
        }
        write_json(args.output_dir / "progress.json", progress)
        print(f"[{index}/{len(plan)}] {item['case_id']} cumulative=${actual_cost:.6f}")

    progress["status"] = "complete_within_budget"
    write_json(args.output_dir / "progress.json", progress)
    print(json.dumps(progress, indent=2))


if __name__ == "__main__":
    main()
