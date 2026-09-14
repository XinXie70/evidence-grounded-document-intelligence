"""Build and execute pinned semantic-answer and citation-support judge requests."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from typing import Any

from .io import canonical_json_bytes, sha256_file, write_json
from .reasoning_api import (
    ResponseProcessingError,
    estimate_cost_usd,
    preflight_request_budget,
    snapshot_api_response,
    validate_pricing_snapshot,
)


JUDGE_TYPES = {"semantic", "support"}


def build_judge_request(record: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    judge_type = record.get("judge_type")
    if judge_type not in JUDGE_TYPES:
        raise ValueError("judge_type must be semantic or support")
    if config.get("provider") != "openai" or config.get("endpoint_mode") != "v1/responses":
        raise ValueError("judge config must use the OpenAI Responses API")
    if config.get("max_retries") != 0:
        raise ValueError("judge retries must be zero")
    expected = "consistent" if judge_type == "semantic" else "supported"
    schema = config.get("response_schema")
    if not isinstance(schema, dict) or expected not in schema.get("properties", {}):
        raise ValueError("judge config schema does not match judge type")
    question = record.get("question")
    candidate = record.get("candidate_answer")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be non-empty")
    if not isinstance(candidate, str) or not candidate.strip():
        raise ValueError("candidate_answer must be non-empty")
    if judge_type == "semantic":
        reference = record.get("reference_answer")
        if not isinstance(reference, str) or not reference.strip():
            raise ValueError("semantic judge requires reference_answer")
        user = f"Question:\n{question}\n\nReference answer:\n{reference}\n\nCandidate answer:\n{candidate}"
    else:
        evidence = record.get("cited_evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError("support judge requires cited_evidence")
        sections = [f"Question:\n{question}", f"Candidate answer:\n{candidate}", "Cited evidence:"]
        for item in evidence:
            if not isinstance(item, dict) or not isinstance(item.get("page"), int):
                raise ValueError("cited evidence item is invalid")
            if not isinstance(item.get("text"), str):
                raise ValueError("cited evidence text must be a string")
            sections.append(f"[Physical PDF page {item['page']}]\n{item['text']}")
        user = "\n\n".join(sections)
    return {
        "model": config["model"],
        "input": [
            {"role": "system", "content": config["instructions"]},
            {"role": "user", "content": user},
        ],
        "reasoning": {"effort": config["reasoning_effort"]},
        "max_output_tokens": config["max_output_tokens"],
        "store": config["store"],
        "text": {
            "format": {
                "type": "json_schema",
                "name": f"calibration_{judge_type}_judgment",
                "strict": True,
                "schema": schema,
            }
        },
    }


def execute_judge(
    record: dict[str, Any], config: dict[str, Any], pricing: dict[str, Any], client: Any,
    *, approved_hard_cap_usd: float,
) -> dict[str, Any]:
    request = build_judge_request(record, config)
    preflight = preflight_request_budget(
        client, request, pricing, approved_hard_cap_usd=approved_hard_cap_usd
    )
    started = time.perf_counter()
    requested_at = datetime.now(timezone.utc).isoformat()
    response = client.responses.create(**request)
    latency_ms = (time.perf_counter() - started) * 1000
    try:
        parsed = json.loads(response.output_text)
    except (json.JSONDecodeError, TypeError) as error:
        raise ResponseProcessingError(
            "judge response did not contain valid structured JSON output",
            response=response,
            cause=error,
        ) from error
    decision_key = "consistent" if record["judge_type"] == "semantic" else "supported"
    if not isinstance(parsed, dict) or not isinstance(parsed.get(decision_key), bool):
        raise ValueError("judge response decision is invalid")
    if not isinstance(parsed.get("reason"), str):
        raise ValueError("judge response reason is invalid")
    usage = response.usage.model_dump() if response.usage is not None else None
    return {
        "schema_version": 1,
        "question_id": record["question_id"],
        "judge_type": record["judge_type"],
        "model": config["model"],
        "response_id": response.id,
        "judgment": parsed,
        "usage": usage,
        "call_log": {
            "experiment_id": config["experiment_id"],
            "provider": config["provider"],
            "model_snapshot": response.model,
            "endpoint_mode": config["endpoint_mode"],
            "request_date_utc": requested_at,
            "latency_ms": round(latency_ms, 3),
            "retries": 0,
            "status": "ok",
            "estimated_cost": estimate_cost_usd(usage, pricing),
            "pricing_snapshot_id": pricing["pricing_snapshot_id"],
            "role": "judge",
        },
        "budget_preflight": preflight,
        "input_sha256": hashlib.sha256(canonical_json_bytes(record)).hexdigest(),
        "config_sha256": hashlib.sha256(canonical_json_bytes(config)).hexdigest(),
        "request_sha256": hashlib.sha256(canonical_json_bytes(request)).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--acknowledge-cost")
    args = parser.parse_args()
    record = json.loads(args.input.read_text(encoding="utf-8"))
    config = json.loads(args.config.read_text(encoding="utf-8"))
    request = build_judge_request(record, config)
    if not args.execute:
        print(json.dumps(request, indent=2))
        return
    from openai import OpenAI
    from .reasoning_api import COST_ACKNOWLEDGEMENT
    if args.acknowledge_cost != COST_ACKNOWLEDGEMENT:
        raise RuntimeError("paid execution requires the exact cost acknowledgement")
    pricing_path = args.config.parent / config["pricing_snapshot_path"]
    pricing = validate_pricing_snapshot(
        json.loads(pricing_path.read_text(encoding="utf-8")), expected_model=config["model"]
    )
    client = OpenAI(max_retries=config["max_retries"])
    try:
        result = execute_judge(record, config, pricing, client, approved_hard_cap_usd=1.0)
    except Exception as error:
        api_response = (
            snapshot_api_response(error.api_response)
            if isinstance(error, ResponseProcessingError)
            else None
        )
        usage = None if api_response is None else api_response["usage"]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        failure_path = args.output.with_name(
            f"{args.output.stem}.failure-{stamp}{args.output.suffix}"
        )
        write_json(failure_path, {
            "schema_version": 1,
            "question_id": record.get("question_id"),
            "judge_type": record.get("judge_type"),
            "api_response": api_response,
            "error": {
                "type": type(error).__name__,
                "cause_type": (
                    type(error.processing_cause).__name__
                    if isinstance(error, ResponseProcessingError) else None
                ),
            },
            "usage": usage,
            "estimated_cost_usd": estimate_cost_usd(usage, pricing),
            "input_sha256": sha256_file(args.input),
            "config_sha256": sha256_file(args.config),
        })
        raise RuntimeError(f"judge attempt metadata written to {failure_path}") from error
    result["input_sha256"] = sha256_file(args.input)
    result["config_sha256"] = sha256_file(args.config)
    write_json(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
