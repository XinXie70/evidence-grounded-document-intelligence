"""Run a frozen K=3/5/10 reasoning smoke test with budget and resume guards."""

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
)


def build_page_budget_plan(
    manifest: dict[str, Any],
    config: dict[str, Any],
    pricing: dict[str, Any],
) -> list[dict[str, Any]]:
    """Validate every frozen input and estimate one paid request per entry."""
    budgets = manifest.get("page_budgets")
    entries = manifest.get("entries")
    if budgets != [3, 5, 10]:
        raise ValueError("manifest page_budgets must be the frozen [3, 5, 10]")
    if not isinstance(entries, list) or len(entries) != manifest.get("request_count"):
        raise ValueError("manifest request count does not match entries")

    seen: set[tuple[str, int]] = set()
    plan: list[dict[str, Any]] = []
    for entry in entries:
        smoke_id = entry.get("smoke_id")
        page_budget = entry.get("page_budget")
        input_path_value = entry.get("path")
        if not isinstance(smoke_id, str) or not smoke_id:
            raise ValueError("entry smoke_id must be a non-empty string")
        if page_budget not in budgets:
            raise ValueError(f"unexpected page budget: {smoke_id}/{page_budget}")
        key = (smoke_id, page_budget)
        if key in seen:
            raise ValueError(f"duplicate entry: {smoke_id}/k{page_budget}")
        seen.add(key)
        if not isinstance(input_path_value, str):
            raise ValueError(f"missing input path: {smoke_id}/k{page_budget}")
        input_path = Path(input_path_value)
        if sha256_file(input_path) != entry.get("sha256"):
            raise ValueError(f"input checksum mismatch: {input_path}")
        record = json.loads(input_path.read_text(encoding="utf-8"))
        if record.get("condition") != "real_retrieval":
            raise ValueError(f"condition must be real_retrieval: {input_path}")
        if record.get("page_budget") != page_budget:
            raise ValueError(f"page-budget mismatch: {input_path}")
        if len(record.get("evidence_pages", [])) != page_budget:
            raise ValueError(f"evidence-page count mismatch: {input_path}")
        if record.get("question_id") != entry.get("question_id"):
            raise ValueError(f"question-id mismatch: {input_path}")

        request = build_openai_request(record, config, input_base_dir=input_path.parent)
        request_bytes = canonical_json_bytes(request)
        estimated_input = math.ceil(len(request_bytes.decode("utf-8")) / 3)
        conservative_cost = (
            estimated_input
            * pricing["input_usd_per_million"]
            * pricing["cache_write_input_multiplier"]
            + config["max_output_tokens"] * pricing["output_usd_per_million"]
        ) / 1_000_000
        plan.append(
            {
                "smoke_id": smoke_id,
                "question_id": record["question_id"],
                "page_budget": page_budget,
                "input_path": str(input_path),
                "input_sha256": entry["sha256"],
                "request_sha256": hashlib.sha256(request_bytes).hexdigest(),
                "conservative_input_tokens": estimated_input,
                "conservative_cost_usd": round(conservative_cost, 9),
            }
        )

    expected = {
        (f"smoke_{index:02d}", budget)
        for index in range(1, manifest.get("case_count", 0) + 1)
        for budget in budgets
    }
    if seen != expected:
        raise ValueError("manifest does not contain the complete smoke-by-budget grid")
    plan.sort(key=lambda item: (item["smoke_id"], item["page_budget"]))
    return plan


def _result_path(output_dir: Path, item: dict[str, Any]) -> Path:
    return output_dir / item["smoke_id"] / f"k{item['page_budget']}.json"


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
        "condition": "real_retrieval",
        "input_sha256": item["input_sha256"],
        "config_sha256": config_sha256,
        "request_sha256": item["request_sha256"],
    }
    for key, value in expected.items():
        if result.get(key) != value:
            raise ValueError(f"existing result {key} mismatch: {path}")
    if result.get("call_log", {}).get("status") != "ok":
        raise ValueError(f"existing result is not successful: {path}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--total-cap-usd", required=True, type=float)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--acknowledge-cost")
    args = parser.parse_args()

    if args.total_cap_usd <= 0:
        raise ValueError("total cap must be positive")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    config = validate_execution_logging_config(
        json.loads(args.config.read_text(encoding="utf-8"))
    )
    pricing_path = args.config.parent / config["pricing_snapshot_path"]
    pricing = validate_pricing_snapshot(
        json.loads(pricing_path.read_text(encoding="utf-8")),
        expected_model=config["model"],
    )
    plan = build_page_budget_plan(manifest, config, pricing)
    conservative_total = round(sum(item["conservative_cost_usd"] for item in plan), 9)
    if conservative_total > args.total_cap_usd:
        raise RuntimeError("conservative batch estimate exceeds total cap")

    preview = {
        "mode": "execute" if args.execute else "dry_run",
        "paid_request_sent": False,
        "request_count": len(plan),
        "conservative_cost_estimate_usd": conservative_total,
        "total_hard_cap_usd": args.total_cap_usd,
        "per_request_hard_cap_usd": config["approved_hard_cap_usd"],
        "output_dir": str(args.output_dir),
        "requests": plan,
    }
    if not args.execute:
        print(json.dumps(preview, indent=2))
        return
    if args.acknowledge_cost != COST_ACKNOWLEDGEMENT:
        raise RuntimeError("paid execution requires the exact cost acknowledgement")
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not configured")

    config_sha256 = sha256_file(args.config)
    actual_cost = 0.0
    completed_count = 0
    for index, item in enumerate(plan, start=1):
        output_path = _result_path(args.output_dir, item)
        result = _load_valid_result(output_path, item, config_sha256=config_sha256)
        if result is None:
            if actual_cost + item["conservative_cost_usd"] > args.total_cap_usd:
                raise RuntimeError("stopped before next request to preserve total cap")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            command = [
                sys.executable,
                "-m",
                "egdi.reasoning_api",
                "--input",
                item["input_path"],
                "--config",
                str(args.config),
                "--output",
                str(output_path),
                "--execute",
                "--acknowledge-cost",
                COST_ACKNOWLEDGEMENT,
            ]
            completed = subprocess.run(command, text=True, capture_output=True)
            if completed.returncode != 0:
                if completed.stderr:
                    print(completed.stderr, file=sys.stderr)
                raise RuntimeError(
                    f"paid request failed at {item['smoke_id']}/k{item['page_budget']}"
                )
            result = _load_valid_result(output_path, item, config_sha256=config_sha256)
            if result is None:
                raise RuntimeError("paid request returned without a result file")
        paid_cost = result["call_log"].get("estimated_cost")
        if isinstance(paid_cost, bool) or not isinstance(paid_cost, (int, float)):
            raise ValueError("result paid cost is invalid")
        actual_cost += paid_cost
        if actual_cost > args.total_cap_usd:
            raise RuntimeError("actual logged cost exceeded total cap")
        completed_count += 1
        progress = {
            **preview,
            "mode": "execute",
            "paid_request_sent": True,
            "completed_requests": completed_count,
            "actual_cost_usd": round(actual_cost, 9),
            "remaining_cap_usd": round(args.total_cap_usd - actual_cost, 9),
        }
        write_json(args.output_dir / "progress.json", progress)
        print(
            f"[{index}/{len(plan)}] {item['smoke_id']}/k{item['page_budget']} "
            f"cumulative=${actual_cost:.6f}"
        )

    final = json.loads((args.output_dir / "progress.json").read_text(encoding="utf-8"))
    final["status"] = "complete_within_budget"
    write_json(args.output_dir / "progress.json", final)
    print(json.dumps(final, indent=2))


if __name__ == "__main__":
    main()
