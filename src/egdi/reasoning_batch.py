"""Run a frozen reasoning-input manifest with deduplication and a budget guard."""

from __future__ import annotations

import argparse
import copy
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
    validate_grounded_output,
    validate_pricing_snapshot,
)


def build_batch_plan(
    manifest: dict[str, Any],
    config: dict[str, Any],
    pricing: dict[str, Any],
) -> list[dict[str, Any]]:
    """Group condition inputs by their condition-blind OpenAI request."""
    conditions = manifest.get("conditions")
    cases = manifest.get("cases")
    if conditions != ["closed_book", "real_retrieval", "oracle_page"]:
        raise ValueError("manifest conditions are not the frozen C0/C1/C2 order")
    if not isinstance(cases, list) or len(cases) != manifest.get("case_count"):
        raise ValueError("manifest case count does not match cases")
    groups: dict[str, dict[str, Any]] = {}
    logical_count = 0
    for case in cases:
        for condition in conditions:
            metadata = case.get(condition)
            if not isinstance(metadata, dict) or not isinstance(metadata.get("path"), str):
                raise ValueError(f"missing input metadata: {case.get('pilot_id')}/{condition}")
            input_path = Path(metadata["path"])
            if sha256_file(input_path) != metadata.get("sha256"):
                raise ValueError(f"input checksum mismatch: {input_path}")
            record = json.loads(input_path.read_text(encoding="utf-8"))
            if record.get("condition") != condition:
                raise ValueError(f"condition mismatch: {input_path}")
            request = build_openai_request(record, config, input_base_dir=input_path.parent)
            request_bytes = canonical_json_bytes(request)
            request_sha256 = hashlib.sha256(request_bytes).hexdigest()
            item = {
                "pilot_id": case["pilot_id"],
                "question_id": case["question_id"],
                "condition": condition,
                "input_path": str(input_path),
                "input_sha256": metadata["sha256"],
            }
            group = groups.setdefault(
                request_sha256,
                {
                    "request_sha256": request_sha256,
                    "canonical_request_characters": len(request_bytes.decode("utf-8")),
                    "items": [],
                },
            )
            group["items"].append(item)
            logical_count += 1

    plan = []
    for request_sha256, group in groups.items():
        group["items"].sort(key=lambda item: (item["pilot_id"], item["condition"]))
        estimated_input = math.ceil(group["canonical_request_characters"] / 3)
        conservative_cost = (
            estimated_input
            * pricing["input_usd_per_million"]
            * pricing["cache_write_input_multiplier"]
            + config["max_output_tokens"] * pricing["output_usd_per_million"]
        ) / 1_000_000
        group["conservative_input_tokens"] = estimated_input
        group["conservative_cost_usd"] = round(conservative_cost, 9)
        plan.append(group)
    plan.sort(key=lambda group: (
        group["items"][0]["pilot_id"], group["items"][0]["condition"]
    ))
    if sum(len(group["items"]) for group in plan) != logical_count:
        raise AssertionError("batch plan lost logical conditions")
    return plan


def _result_path(output_dir: Path, item: dict[str, Any]) -> Path:
    return output_dir / item["pilot_id"] / f"{item['condition']}.json"


def _load_valid_result(
    path: Path,
    item: dict[str, Any],
    *,
    config_sha256: str,
    request_sha256: str,
) -> dict[str, Any] | None:
    if not path.exists():
        return None
    result = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "question_id": item["question_id"],
        "condition": item["condition"],
        "input_sha256": item["input_sha256"],
        "config_sha256": config_sha256,
        "request_sha256": request_sha256,
    }
    for key, value in expected.items():
        if result.get(key) != value:
            raise ValueError(f"existing result {key} mismatch: {path}")
    if result.get("call_log", {}).get("status") != "ok":
        raise ValueError(f"existing result is not successful: {path}")
    return result


def _write_reused_result(
    source: dict[str, Any],
    source_path: Path,
    target_item: dict[str, Any],
    target_path: Path,
) -> dict[str, Any]:
    record = json.loads(Path(target_item["input_path"]).read_text(encoding="utf-8"))
    reused = copy.deepcopy(source)
    reused["question_id"] = record["question_id"]
    reused["doc_id"] = record["doc_id"]
    reused["condition"] = record["condition"]
    reused["evidence_pages"] = record["evidence_pages"]
    reused["validation"] = validate_grounded_output(
        reused["output"],
        record["evidence_pages"],
        allow_uncited_answer=record["condition"] == "closed_book",
    )
    reused["input_sha256"] = target_item["input_sha256"]
    original_cost = reused["call_log"]["estimated_cost"]
    reused["call_log"]["estimated_cost"] = 0.0
    reused["deduplication"] = {
        "paid_request_reused": True,
        "source_result": str(source_path),
        "source_paid_estimated_cost_usd": original_cost,
        "incremental_cost_usd": 0.0,
    }
    write_json(target_path, reused)
    return reused


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
    conservative_total = round(sum(g["conservative_cost_usd"] for g in plan), 9)
    if len(plan) != budget.get("unique_paid_request_count"):
        raise ValueError("unique request count differs from approved budget")
    if conservative_total > cap:
        raise RuntimeError("conservative batch estimate exceeds approved hard cap")

    preview = {
        "mode": "execute" if args.execute else "dry_run",
        "paid_request_sent": False,
        "logical_condition_count": sum(len(g["items"]) for g in plan),
        "unique_request_count": len(plan),
        "deduplicated_condition_count": sum(len(g["items"]) - 1 for g in plan),
        "conservative_cost_estimate_usd": conservative_total,
        "approved_hard_cap_usd": cap,
        "output_dir": str(args.output_dir),
    }
    if not args.execute:
        print(json.dumps(preview, indent=2))
        return
    if args.acknowledge_cost != COST_ACKNOWLEDGEMENT:
        raise RuntimeError("paid execution requires the exact cost acknowledgement")
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not configured")

    actual_cost = 0.0
    completed_unique = 0
    completed_logical = 0
    for index, group in enumerate(plan, start=1):
        existing = []
        for item in group["items"]:
            path = _result_path(args.output_dir, item)
            result = _load_valid_result(
                path,
                item,
                config_sha256=config_sha256,
                request_sha256=group["request_sha256"],
            )
            if result is not None:
                existing.append((item, path, result))
        paid_existing = [
            row for row in existing
            if not row[2].get("deduplication", {}).get("paid_request_reused", False)
        ]
        if len(paid_existing) > 1:
            raise ValueError("duplicate paid results exist for one request")
        if paid_existing:
            source_item, source_path, source = paid_existing[0]
        else:
            if actual_cost + group["conservative_cost_usd"] > cap:
                raise RuntimeError("stopped before next request to preserve approved cap")
            source_item = group["items"][0]
            source_path = _result_path(args.output_dir, source_item)
            source_path.parent.mkdir(parents=True, exist_ok=True)
            command = [
                sys.executable,
                "-m",
                "egdi.reasoning_api",
                "--input",
                source_item["input_path"],
                "--config",
                str(args.config),
                "--output",
                str(source_path),
                "--execute",
                "--acknowledge-cost",
                COST_ACKNOWLEDGEMENT,
            ]
            completed = subprocess.run(command, text=True, capture_output=True)
            if completed.returncode != 0:
                if completed.stderr:
                    print(completed.stderr, file=sys.stderr)
                raise RuntimeError(f"paid request failed at {source_item['pilot_id']}/{source_item['condition']}")
            source = _load_valid_result(
                source_path,
                source_item,
                config_sha256=config_sha256,
                request_sha256=group["request_sha256"],
            )
            if source is None:
                raise RuntimeError("paid request returned without a result file")
        paid_cost = source["call_log"]["estimated_cost"]
        if isinstance(paid_cost, bool) or not isinstance(paid_cost, (int, float)):
            raise ValueError("result paid cost is invalid")
        actual_cost += paid_cost
        if actual_cost > cap:
            raise RuntimeError("actual logged cost exceeded approved cap")

        for item in group["items"]:
            target_path = _result_path(args.output_dir, item)
            if target_path == source_path:
                continue
            if not target_path.exists():
                target_path.parent.mkdir(parents=True, exist_ok=True)
                _write_reused_result(source, source_path, item, target_path)
        completed_unique += 1
        completed_logical += len(group["items"])
        progress = {
            **preview,
            "mode": "execute",
            "paid_request_sent": True,
            "completed_unique_requests": completed_unique,
            "completed_logical_conditions": completed_logical,
            "actual_cost_usd": round(actual_cost, 9),
            "remaining_cap_usd": round(cap - actual_cost, 9),
        }
        write_json(args.output_dir / "progress.json", progress)
        print(
            f"[{index}/{len(plan)}] {source_item['pilot_id']}/{source_item['condition']} "
            f"cumulative=${actual_cost:.6f}"
        )

    final = json.loads((args.output_dir / "progress.json").read_text(encoding="utf-8"))
    final["status"] = "complete_within_budget"
    write_json(args.output_dir / "progress.json", final)
    print(json.dumps(final, indent=2))


if __name__ == "__main__":
    main()
