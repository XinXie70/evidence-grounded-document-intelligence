"""Budget and execute the frozen calibration semantic/support judge batch."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from .access import require_evaluation_split_access
from .calibration_judge import build_judge_request
from .io import canonical_json_bytes, sha256_file, write_json
from .reasoning_api import COST_ACKNOWLEDGEMENT, validate_pricing_snapshot


def build_plan(manifest: dict[str, Any], configs: dict[str, tuple[Path, dict[str, Any]]], pricing: dict[str, Any]) -> list[dict[str, Any]]:
    split = manifest.get("split")
    if split not in {"development_calibration", "locked_test"}:
        raise ValueError("judge manifest must be development_calibration or locked_test")
    require_evaluation_split_access(split)
    plan = []
    for case in manifest.get("cases", []):
        for judge_type in ("semantic", "support"):
            metadata = case.get(f"{judge_type}_input")
            if metadata is None:
                continue
            path = Path(metadata["path"])
            if sha256_file(path) != metadata["sha256"]:
                raise ValueError(f"judge input checksum mismatch: {path}")
            config_path, config = configs[judge_type]
            record = json.loads(path.read_text(encoding="utf-8"))
            request = build_judge_request(record, config)
            estimated_input = math.ceil(len(canonical_json_bytes(request).decode("utf-8")) / 3)
            conservative = (
                estimated_input * pricing["input_usd_per_million"] * pricing["cache_write_input_multiplier"]
                + config["max_output_tokens"] * pricing["output_usd_per_million"]
            ) / 1_000_000
            plan.append({
                "pilot_id": case["pilot_id"], "question_id": case["question_id"],
                "judge_type": judge_type, "input_path": str(path),
                "input_sha256": metadata["sha256"], "config_path": str(config_path),
                "config_sha256": sha256_file(config_path),
                "conservative_input_tokens": estimated_input,
                "conservative_cost_usd": round(conservative, 9),
            })
    return plan


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--semantic-config", required=True, type=Path)
    parser.add_argument("--support-config", required=True, type=Path)
    parser.add_argument("--support-fallback-config", type=Path)
    parser.add_argument("--budget", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--acknowledge-cost")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    configs = {
        "semantic": (args.semantic_config, json.loads(args.semantic_config.read_text())),
        "support": (args.support_config, json.loads(args.support_config.read_text())),
    }
    fallback_config = (
        None
        if args.support_fallback_config is None
        else json.loads(args.support_fallback_config.read_text())
    )
    pricing_path = args.semantic_config.parent / configs["semantic"][1]["pricing_snapshot_path"]
    pricing = validate_pricing_snapshot(json.loads(pricing_path.read_text()), expected_model=configs["semantic"][1]["model"])
    plan = build_plan(manifest, configs, pricing)
    conservative_total = round(sum(item["conservative_cost_usd"] for item in plan), 9)
    preview = {
        "mode": "execute" if args.execute else "dry_run", "paid_request_sent": False,
        "case_count": manifest["case_count"], "judge_request_count": len(plan),
        "semantic_request_count": sum(x["judge_type"] == "semantic" for x in plan),
        "support_request_count": sum(x["judge_type"] == "support" for x in plan),
        "conservative_cost_estimate_usd": conservative_total, "output_dir": str(args.output_dir),
    }
    if not args.execute:
        print(json.dumps(preview, indent=2))
        return
    if args.budget is None:
        raise ValueError("paid execution requires --budget")
    budget = json.loads(args.budget.read_text())
    if budget.get("status") != "approved_not_started":
        raise ValueError("budget must be approved_not_started")
    if budget.get("input_manifest_sha256") != sha256_file(args.manifest):
        raise ValueError("budget/input manifest checksum mismatch")
    if budget.get("semantic_config_sha256") != sha256_file(args.semantic_config) or budget.get("support_config_sha256") != sha256_file(args.support_config):
        raise ValueError("budget/config checksum mismatch")
    fallback_requests = budget.get("operational_fallback_requests", {})
    if not isinstance(fallback_requests, dict):
        raise ValueError("operational fallback request map is invalid")
    if fallback_requests:
        if args.support_fallback_config is None or fallback_config is None:
            raise ValueError("approved operational fallback config is required")
        if budget.get("support_fallback_config_sha256") != sha256_file(args.support_fallback_config):
            raise ValueError("budget/fallback-config checksum mismatch")
    cap = budget.get("approved_hard_cap_usd")
    failed_reserve = budget.get(
        "prior_accounted_cost_usd",
        budget.get("prior_failed_request_reserve_usd", 0.0),
    )
    if isinstance(failed_reserve, bool) or not isinstance(failed_reserve, (int, float)) or failed_reserve < 0:
        raise ValueError("prior failed request reserve is invalid")
    fallback_delta = sum(
        item.get("additional_conservative_cost_usd", 0.0)
        for item in fallback_requests.values()
        if isinstance(item, dict)
    )
    if conservative_total + failed_reserve + fallback_delta > cap:
        raise RuntimeError("conservative batch estimate plus failed-request reserve exceeds approved cap")
    if args.acknowledge_cost != COST_ACKNOWLEDGEMENT:
        raise RuntimeError("paid execution requires exact cost acknowledgement")
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not configured")
    actual = 0.0
    for index, item in enumerate(plan, 1):
        output_path = args.output_dir / item["pilot_id"] / f"{item['judge_type']}.json"
        request_key = f"{item['pilot_id']}/{item['judge_type']}"
        execution_config_path = Path(item["config_path"])
        execution_config_sha256 = item["config_sha256"]
        if request_key in fallback_requests:
            if item["judge_type"] != "support":
                raise ValueError("only support-judge operational fallback is supported")
            execution_config_path = args.support_fallback_config
            execution_config_sha256 = sha256_file(execution_config_path)
        if output_path.exists():
            result = json.loads(output_path.read_text())
            if result.get("input_sha256") != item["input_sha256"] or result.get("config_sha256") != execution_config_sha256:
                raise ValueError(f"existing judge result failed validation: {output_path}")
        else:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            command = [sys.executable, "-m", "egdi.calibration_judge", "--input", item["input_path"], "--config", str(execution_config_path), "--output", str(output_path), "--execute", "--acknowledge-cost", COST_ACKNOWLEDGEMENT]
            call = subprocess.run(command, text=True, capture_output=True)
            if call.returncode:
                if call.stderr:
                    print(call.stderr, file=sys.stderr)
                raise RuntimeError(f"judge request failed at {item['pilot_id']}/{item['judge_type']}")
            result = json.loads(output_path.read_text())
        actual += result["call_log"]["estimated_cost"]
        accounted = actual + failed_reserve
        if accounted > cap:
            raise RuntimeError("actual judge cost exceeded approved cap")
        write_json(args.output_dir / "progress.json", {**preview, "mode": "execute", "paid_request_sent": True, "completed_requests": index, "successful_request_cost_usd": round(actual, 9), "prior_failed_request_reserve_usd": round(failed_reserve, 9), "budget_accounted_cost_usd": round(accounted, 9), "remaining_cap_usd": round(cap-accounted, 9)})
        print(f"[{index}/{len(plan)}] {item['pilot_id']}/{item['judge_type']} cumulative=${actual:.6f}", flush=True)
    final = json.loads((args.output_dir / "progress.json").read_text())
    final["status"] = "complete_within_budget"
    write_json(args.output_dir / "progress.json", final)
    if args.budget.exists():
        completed_budget = dict(budget)
        completed_budget.update({"status": "complete_within_budget", "successful_request_cost_usd": round(actual, 9), "budget_accounted_cost_usd": round(actual + failed_reserve, 9), "completed_request_count": len(plan)})
        write_json(args.budget, completed_budget)
    print(json.dumps(final, indent=2))


if __name__ == "__main__":
    main()
