"""Dry-run or execute the single-condition V1 confidence-tune reasoning batch."""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .access import require_evaluation_split_access
from .io import canonical_json_bytes, sha256_file, write_json
from .reasoning_api import (
    COST_ACKNOWLEDGEMENT,
    build_openai_request,
    validate_execution_logging_config,
    validate_pricing_snapshot,
)
from .visual_routing import ROUTE_DOCUMENT_GLOBAL


def build_v1_batch_plan(
    manifest: dict[str, Any], config: dict[str, Any], pricing: dict[str, Any]
) -> list[dict[str, Any]]:
    """Validate immutable inputs and estimate only requests allowed by the route policy."""
    split = manifest.get("split")
    if split not in {"development_tune", "development_calibration", "locked_test"}:
        raise ValueError("unknown evaluation split")
    require_evaluation_split_access(split)
    if manifest.get("contains_gold_or_answer_labels") is not False:
        raise ValueError("manifest must explicitly exclude benchmark labels")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or len(cases) != manifest.get("case_count"):
        raise ValueError("manifest case count mismatch")
    plan = []
    seen: set[str] = set()
    for case in cases:
        question_id = case.get("question_id")
        pilot_id = case.get("pilot_id")
        if not isinstance(question_id, str) or not isinstance(pilot_id, str):
            raise ValueError("case identity is invalid")
        if question_id in seen:
            raise ValueError(f"duplicate question_id: {question_id}")
        seen.add(question_id)
        paid = case.get("paid_request_required")
        if not isinstance(paid, bool):
            raise ValueError("paid_request_required must be boolean")
        if case.get("route") == ROUTE_DOCUMENT_GLOBAL:
            if paid or case.get("evidence_pages") != []:
                raise ValueError("R3 must be a zero-evidence local abstention")
            continue
        if not paid:
            raise ValueError("non-R3 cases must require one reasoning request")
        metadata = case.get("reasoning_input")
        if not isinstance(metadata, dict) or not isinstance(metadata.get("path"), str):
            raise ValueError("case reasoning input metadata is invalid")
        input_path = Path(metadata["path"])
        if sha256_file(input_path) != metadata.get("sha256"):
            raise ValueError(f"reasoning input checksum mismatch: {input_path}")
        record = json.loads(input_path.read_text(encoding="utf-8"))
        if record.get("question_id") != question_id or record.get("condition") != "real_retrieval":
            raise ValueError(f"reasoning input identity drift: {input_path}")
        request = build_openai_request(record, config, input_base_dir=input_path.parent)
        characters = len(canonical_json_bytes(request).decode("utf-8"))
        estimated_input = math.ceil(characters / 3)
        conservative_cost = (
            estimated_input
            * pricing["input_usd_per_million"]
            * pricing["cache_write_input_multiplier"]
            + config["max_output_tokens"] * pricing["output_usd_per_million"]
        ) / 1_000_000
        plan.append(
            {
                "pilot_id": pilot_id,
                "question_id": question_id,
                "input_path": str(input_path),
                "input_sha256": metadata["sha256"],
                "request_sha256": __import__("hashlib").sha256(
                    canonical_json_bytes(request)
                ).hexdigest(),
                "conservative_input_tokens": estimated_input,
                "conservative_cost_usd": round(conservative_cost, 9),
            }
        )
    return plan


def _result_path(output_dir: Path, item: dict[str, Any]) -> Path:
    return output_dir / item["pilot_id"] / "real_retrieval.json"


def _validate_existing(
    path: Path, item: dict[str, Any], *, config_sha256: str
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


def _write_r3_abstentions(manifest: dict[str, Any], output_dir: Path) -> None:
    for case in manifest["cases"]:
        if case["route"] != ROUTE_DOCUMENT_GLOBAL:
            continue
        path = output_dir / case["pilot_id"] / "real_retrieval.json"
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing.get("question_id") != case["question_id"]:
                raise ValueError(f"existing R3 result identity mismatch: {path}")
            continue
        write_json(
            path,
            {
                "schema_version": 1,
                "question_id": case["question_id"],
                "doc_id": case["doc_id"],
                "condition": "real_retrieval",
                "evidence_pages": [],
                "model": "deterministic_r3_policy",
                "response_id": None,
                "output": {
                    "answer": None,
                    "cited_pages": [],
                    "status": "insufficient_evidence",
                },
                "validation": {
                    "valid": True,
                    "citations_within_supplied_context": True,
                    "errors": [],
                },
                "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                "call_log": {
                    "status": "not_sent_policy_abstention",
                    "estimated_cost": 0.0,
                    "role": "answer_generation",
                },
                "policy": {
                    "route": ROUTE_DOCUMENT_GLOBAL,
                    "paid_request_sent": False,
                },
            },
        )


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
    config = validate_execution_logging_config(json.loads(args.config.read_text(encoding="utf-8")))
    pricing_path = args.config.parent / config["pricing_snapshot_path"]
    pricing = validate_pricing_snapshot(
        json.loads(pricing_path.read_text(encoding="utf-8")), expected_model=config["model"]
    )
    budget = json.loads(args.budget.read_text(encoding="utf-8"))
    config_sha256 = sha256_file(args.config)
    if budget.get("config_sha256") != config_sha256:
        raise ValueError("budget/config checksum mismatch")
    if budget.get("input_manifest_sha256") != sha256_file(args.manifest):
        raise ValueError("budget/input-manifest checksum mismatch")
    cap = budget.get("approved_hard_cap_usd")
    if isinstance(cap, bool) or not isinstance(cap, (int, float)) or cap <= 0:
        raise ValueError("budget hard cap must be a positive number")
    plan = build_v1_batch_plan(manifest, config, pricing)
    if len(plan) != budget.get("unique_paid_request_count"):
        raise ValueError("request count differs from budget")
    conservative_total = round(sum(item["conservative_cost_usd"] for item in plan), 9)
    if conservative_total > cap:
        raise RuntimeError("conservative batch estimate exceeds approved hard cap")
    preview = {
        "mode": "execute" if args.execute else "dry_run",
        "paid_request_sent": False,
        "case_count": manifest["case_count"],
        "unique_paid_request_count": len(plan),
        "local_policy_abstention_count": manifest["case_count"] - len(plan),
        "conservative_cost_estimate_usd": conservative_total,
        "approved_hard_cap_usd": float(cap),
        "output_dir": str(args.output_dir),
    }
    if not args.execute:
        if budget.get("status") not in {"proposed_not_started", "approved_not_started"}:
            raise ValueError("budget status does not permit dry-run")
        print(json.dumps({**preview, "requests": plan}, indent=2))
        return

    if budget.get("status") != "approved_not_started":
        raise ValueError("paid execution requires an approved_not_started budget")
    if args.acknowledge_cost != COST_ACKNOWLEDGEMENT:
        raise RuntimeError("paid execution requires the exact cost acknowledgement")
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not configured")

    actual_cost = 0.0
    completed = 0
    for index, item in enumerate(plan, start=1):
        path = _result_path(args.output_dir, item)
        result = _validate_existing(path, item, config_sha256=config_sha256)
        if result is None:
            if actual_cost + item["conservative_cost_usd"] > cap:
                raise RuntimeError("stopped before next request to preserve the batch cap")
            path.parent.mkdir(parents=True, exist_ok=True)
            command = [
                sys.executable,
                "-m",
                "egdi.reasoning_api",
                "--input",
                item["input_path"],
                "--config",
                str(args.config),
                "--output",
                str(path),
                "--execute",
                "--acknowledge-cost",
                COST_ACKNOWLEDGEMENT,
            ]
            call = subprocess.run(command, text=True, capture_output=True)
            if call.returncode != 0:
                if call.stderr:
                    print(call.stderr, file=sys.stderr)
                raise RuntimeError(f"paid request failed at {item['pilot_id']}")
            result = _validate_existing(path, item, config_sha256=config_sha256)
            if result is None:
                raise RuntimeError("paid request returned without a result file")
        cost = result["call_log"]["estimated_cost"]
        if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost < 0:
            raise ValueError("logged result cost is invalid")
        actual_cost += cost
        if actual_cost > cap:
            raise RuntimeError("actual logged cost exceeded the batch cap")
        completed += 1
        progress = {
            **preview,
            "mode": "execute",
            "paid_request_sent": True,
            "completed_paid_requests": completed,
            "actual_cost_usd": round(actual_cost, 9),
            "remaining_cap_usd": round(cap - actual_cost, 9),
        }
        write_json(args.output_dir / "progress.json", progress)
        print(f"[{index}/{len(plan)}] {item['pilot_id']} cumulative=${actual_cost:.6f}", flush=True)

    _write_r3_abstentions(manifest, args.output_dir)
    final = json.loads((args.output_dir / "progress.json").read_text(encoding="utf-8"))
    final["status"] = "complete_within_budget"
    write_json(args.output_dir / "progress.json", final)
    print(json.dumps(final, indent=2))


if __name__ == "__main__":
    main()
