"""Preview or execute one guarded OpenAI grounded-reasoning request."""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any

from .io import canonical_json_bytes, sha256_file, write_json


COST_ACKNOWLEDGEMENT = "I_ACKNOWLEDGE_ONE_PAID_REASONING_REQUEST"
FORBIDDEN_MODEL_INPUT_KEYS = {"answer_text", "is_answerable", "condition"}


class ResponseProcessingError(RuntimeError):
    """Preserve an API response when local parsing or validation fails."""

    def __init__(self, message: str, *, response: Any, cause: Exception):
        super().__init__(message)
        self.api_response = response
        self.processing_cause = cause


class BudgetPreflightError(RuntimeError):
    """Raised before answer generation when its conservative cap would be exceeded."""


def _read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _find_forbidden_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in FORBIDDEN_MODEL_INPUT_KEYS:
                found.add(key)
            found.update(_find_forbidden_keys(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_find_forbidden_keys(item))
    return found


def _render_user_content(model_input: dict[str, Any]) -> str:
    question = model_input.get("question")
    evidence = model_input.get("evidence")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("model_input.question must be a non-empty string")
    if not isinstance(evidence, list):
        raise ValueError("model_input.evidence must be a list")

    sections = [f"Question:\n{question}", "Document evidence:"]
    if not evidence:
        sections.append("(No document evidence supplied.)")
    for item in evidence:
        if not isinstance(item, dict):
            raise ValueError("each evidence item must be an object")
        page = item.get("page")
        text = item.get("text")
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise ValueError("evidence page must be a positive integer")
        if not isinstance(text, str):
            raise ValueError("evidence text must be a string")
        sections.append(f"[Physical PDF page {page}]\n{text}")
    return "\n\n".join(sections)


def _render_user_content_with_images(
    model_input: dict[str, Any], *, input_base_dir: Path, image_detail: str
) -> list[dict[str, Any]]:
    question = model_input.get("question")
    evidence = model_input.get("evidence")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("model_input.question must be a non-empty string")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("image model_input.evidence must be a non-empty list")
    base_dir = input_base_dir.resolve()
    parts: list[dict[str, Any]] = [
        {
            "type": "input_text",
            "text": f"Question:\n{question}\n\nDocument evidence regions:",
        }
    ]
    for item in evidence:
        if not isinstance(item, dict):
            raise ValueError("each evidence item must be an object")
        page = item.get("page")
        text = item.get("text")
        text_scope = item.get("text_scope")
        image_path = item.get("image_path")
        expected_sha256 = item.get("image_sha256")
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise ValueError("evidence page must be a positive integer")
        if not isinstance(text, str):
            raise ValueError("evidence text must be a string")
        if not isinstance(image_path, str) or not image_path:
            raise ValueError("image evidence must provide image_path")
        if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
            raise ValueError("image evidence must provide image_sha256")
        resolved = (base_dir / image_path).resolve()
        if not resolved.is_relative_to(base_dir):
            raise ValueError("image_path must remain within the input directory")
        if resolved.suffix.lower() != ".png" or not resolved.is_file():
            raise ValueError(f"image evidence must reference an existing PNG: {image_path}")
        if sha256_file(resolved) != expected_sha256:
            raise ValueError(f"image checksum mismatch: {image_path}")
        label = (
            f"[Physical PDF page {page}; evidence region "
            f"{item.get('evidence_local_id')}; bbox {item.get('bbox')}]"
        )
        if text:
            label += f"\nNative text intersecting the region:\n{text}"
        elif text_scope == "image_only":
            label += "\n(Native text was intentionally omitted; use the supplied image.)"
        else:
            label += "\n(No native text was available for this region.)"
        parts.append({"type": "input_text", "text": label})
        encoded = base64.b64encode(resolved.read_bytes()).decode("ascii")
        parts.append(
            {
                "type": "input_image",
                "image_url": f"data:image/png;base64,{encoded}",
                "detail": image_detail,
            }
        )
    return parts


def build_openai_request(
    experiment_record: dict[str, Any],
    config: dict[str, Any],
    *,
    input_base_dir: Path | None = None,
) -> dict[str, Any]:
    """Create a condition-blind Responses API payload without making a request."""
    model_input = experiment_record.get("model_input")
    if not isinstance(model_input, dict):
        raise ValueError("experiment record is missing model_input")
    forbidden = _find_forbidden_keys(model_input)
    if forbidden:
        raise ValueError(f"forbidden keys in model_input: {sorted(forbidden)}")

    instructions = model_input.get("instructions")
    response_schema = model_input.get("response_schema")
    if not isinstance(instructions, str) or not instructions.strip():
        raise ValueError("model_input.instructions must be a non-empty string")
    if not isinstance(response_schema, dict):
        raise ValueError("model_input.response_schema must be an object")

    model = config.get("model")
    effort = config.get("reasoning_effort")
    max_output_tokens = config.get("max_output_tokens")
    store = config.get("store")
    evidence = model_input.get("evidence")
    has_images = isinstance(evidence, list) and any(
        isinstance(item, dict) and "image_path" in item for item in evidence
    )
    if not isinstance(model, str) or not model:
        raise ValueError("config.model must be a non-empty string")
    if effort not in {"none", "low", "medium", "high", "xhigh", "max"}:
        raise ValueError("config.reasoning_effort is invalid")
    if (
        isinstance(max_output_tokens, bool)
        or not isinstance(max_output_tokens, int)
        or max_output_tokens < 1
    ):
        raise ValueError("config.max_output_tokens must be a positive integer")
    if not isinstance(store, bool):
        raise ValueError("config.store must be boolean")
    if has_images:
        image_detail = config.get("image_detail")
        if image_detail not in {"low", "high", "original", "auto"}:
            raise ValueError("image requests require a pinned config.image_detail")
        if input_base_dir is None:
            raise ValueError("image requests require input_base_dir")
        user_content: Any = _render_user_content_with_images(
            model_input,
            input_base_dir=input_base_dir,
            image_detail=image_detail,
        )
    else:
        user_content = _render_user_content(model_input)

    return {
        "model": model,
        "input": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": user_content},
        ],
        "reasoning": {"effort": effort},
        "max_output_tokens": max_output_tokens,
        "store": store,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "grounded_document_answer",
                "strict": True,
                "schema": response_schema,
            }
        },
    }


def validate_grounded_output(
    parsed: dict[str, Any],
    supplied_pages: list[int],
    *,
    allow_uncited_answer: bool = False,
) -> dict[str, Any]:
    """Check grounding constraints that JSON Schema alone cannot enforce."""
    errors: list[str] = []
    cited_pages = parsed.get("cited_pages")
    answer = parsed.get("answer")
    status = parsed.get("status")
    if not isinstance(cited_pages, list) or any(
        isinstance(page, bool) or not isinstance(page, int) for page in cited_pages
    ):
        errors.append("cited_pages is not a list of integers")
        cited_pages = []
    elif len(cited_pages) != len(set(cited_pages)):
        errors.append("cited_pages contains duplicates")
    outside = sorted(set(cited_pages) - set(supplied_pages))
    if outside:
        errors.append(f"cited pages were not supplied: {outside}")
    if status == "insufficient_evidence":
        if answer is not None:
            errors.append("insufficient_evidence must have answer=null")
        if cited_pages:
            errors.append("insufficient_evidence must have no cited pages")
    elif status == "answerable":
        if not isinstance(answer, str) or not answer.strip():
            errors.append("answerable must have a non-empty answer")
        if not cited_pages and not allow_uncited_answer:
            errors.append("answerable must cite at least one supplied page")
    else:
        errors.append("status is invalid")
    return {
        "valid": not errors,
        "citations_within_supplied_context": not outside,
        "errors": errors,
    }


def validate_execution_logging_config(config: dict[str, Any]) -> dict[str, Any]:
    """Validate metadata required for protocol-compliant paid-call logging."""
    required_strings = (
        "experiment_id",
        "provider",
        "endpoint_mode",
        "pricing_snapshot_path",
    )
    for key in required_strings:
        value = config.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"config.{key} must be a non-empty string")
    if config["provider"] != "openai":
        raise ValueError("config.provider must be 'openai'")
    if config["endpoint_mode"] != "v1/responses":
        raise ValueError("config.endpoint_mode must be 'v1/responses'")
    max_retries = config.get("max_retries")
    if isinstance(max_retries, bool) or max_retries != 0:
        raise ValueError("config.max_retries must be 0 so retries are exactly observable")
    return config


def validate_pricing_snapshot(
    pricing: dict[str, Any], *, expected_model: str
) -> dict[str, Any]:
    """Validate the versioned pricing inputs used for cost estimates."""
    required_strings = ("pricing_snapshot_id", "provider", "model", "currency", "source_url")
    for key in required_strings:
        value = pricing.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"pricing.{key} must be a non-empty string")
    if pricing["provider"] != "openai":
        raise ValueError("pricing.provider must be 'openai'")
    if pricing["model"] != expected_model:
        raise ValueError("pricing.model does not match config.model")
    if pricing["currency"] != "USD":
        raise ValueError("pricing.currency must be 'USD'")
    for key in (
        "input_usd_per_million",
        "cached_input_usd_per_million",
        "output_usd_per_million",
        "cache_write_input_multiplier",
    ):
        value = pricing.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ValueError(f"pricing.{key} must be a non-negative number")
    return pricing


def estimate_cost_usd(usage: dict[str, Any] | None, pricing: dict[str, Any]) -> float:
    """Estimate one response's USD cost from logged token categories."""
    if usage is None:
        return 0.0
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    details = usage.get("input_tokens_details") or {}
    cached_tokens = details.get("cached_tokens", 0)
    cache_write_tokens = details.get("cache_write_tokens", 0)
    counts = (input_tokens, output_tokens, cached_tokens, cache_write_tokens)
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts):
        raise ValueError("usage token counts must be non-negative integers")
    ordinary_input_tokens = input_tokens - cached_tokens - cache_write_tokens
    if ordinary_input_tokens < 0:
        raise ValueError("cached and cache-write tokens exceed total input tokens")
    cost = (
        ordinary_input_tokens * pricing["input_usd_per_million"]
        + cached_tokens * pricing["cached_input_usd_per_million"]
        + cache_write_tokens
        * pricing["input_usd_per_million"]
        * pricing["cache_write_input_multiplier"]
        + output_tokens * pricing["output_usd_per_million"]
    ) / 1_000_000
    return round(cost, 9)


def validate_single_request_cap(value: Any) -> float:
    """Return a positive, non-boolean USD cap."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError("approved single-request hard cap must be a positive number")
    return float(value)


def load_single_request_cap(config: dict[str, Any], *, config_path: Path) -> float:
    """Resolve an explicit config cap or the repository-wide standing policy cap."""
    explicit = config.get("approved_hard_cap_usd")
    if explicit is not None:
        return validate_single_request_cap(explicit)
    policy_path = config_path.parent / "paid_request_policy_v0.json"
    if not policy_path.is_file():
        raise ValueError(
            "no approved_hard_cap_usd in config and no paid-request policy found"
        )
    policy = _read_json_object(policy_path)
    if policy.get("status") != "active":
        raise ValueError("paid-request policy is not active")
    single_request = policy.get("single_request")
    if not isinstance(single_request, dict) or not single_request.get(
        "requests_above_cap_must_be_blocked_before_execution"
    ):
        raise ValueError("paid-request policy does not require pre-execution blocking")
    return validate_single_request_cap(single_request.get("approved_hard_cap_usd"))


def preflight_request_budget(
    client: Any,
    request: dict[str, Any],
    pricing: dict[str, Any],
    *,
    approved_hard_cap_usd: float,
) -> dict[str, Any]:
    """Count multimodal input tokens and block generation above the approved cap."""
    cap = validate_single_request_cap(approved_hard_cap_usd)
    max_output_tokens = request.get("max_output_tokens")
    if (
        isinstance(max_output_tokens, bool)
        or not isinstance(max_output_tokens, int)
        or max_output_tokens < 1
    ):
        raise ValueError("request.max_output_tokens must be a positive integer")
    countable_request = {
        key: request[key]
        for key in ("model", "input", "reasoning", "text")
        if key in request
    }
    token_count = client.responses.input_tokens.count(**countable_request)
    input_tokens = getattr(token_count, "input_tokens", None)
    if isinstance(input_tokens, bool) or not isinstance(input_tokens, int) or input_tokens < 0:
        raise ValueError("input-token count response is invalid")
    worst_input_rate = max(
        pricing["input_usd_per_million"],
        pricing["cached_input_usd_per_million"],
        pricing["input_usd_per_million"] * pricing["cache_write_input_multiplier"],
    )
    conservative_cost = round(
        (
            input_tokens * worst_input_rate
            + max_output_tokens * pricing["output_usd_per_million"]
        )
        / 1_000_000,
        9,
    )
    result = {
        "input_tokens": input_tokens,
        "max_output_tokens": max_output_tokens,
        "conservative_cost_usd": conservative_cost,
        "approved_hard_cap_usd": cap,
        "within_cap": conservative_cost <= cap,
    }
    if not result["within_cap"]:
        raise BudgetPreflightError(
            f"blocked before answer generation: conservative estimate "
            f"${conservative_cost:.6f} exceeds ${cap:.6f} hard cap"
        )
    return result


def build_call_log(
    experiment_record: dict[str, Any],
    config: dict[str, Any],
    request: dict[str, Any],
    pricing: dict[str, Any],
    *,
    model_snapshot: str,
    usage: dict[str, Any] | None,
    request_date_utc: str,
    latency_ms: float,
    status: str,
) -> dict[str, Any]:
    """Build one call-log record matching the frozen experiment log schema."""
    if status not in {"ok", "error"}:
        raise ValueError("call status must be 'ok' or 'error'")
    input_tokens = 0 if usage is None else usage.get("input_tokens", 0)
    output_tokens = 0 if usage is None else usage.get("output_tokens", 0)
    details = {} if usage is None else usage.get("input_tokens_details") or {}
    cached_input_tokens = details.get("cached_tokens", 0)
    doc_id = experiment_record.get("doc_id")
    context_ids = [
        f"{doc_id}::physical_page:{page}"
        for page in experiment_record.get("evidence_pages", [])
    ]
    prompt_sha256 = hashlib.sha256(canonical_json_bytes(request["input"])).hexdigest()
    return {
        "experiment_id": config["experiment_id"],
        "question_id": experiment_record.get("question_id"),
        "provider": config["provider"],
        "model_snapshot": model_snapshot,
        "endpoint_mode": config["endpoint_mode"],
        "request_date_utc": request_date_utc,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_input_tokens": cached_input_tokens,
        "latency_ms": round(latency_ms, 3),
        "retries": 0,
        "status": status,
        "estimated_cost": estimate_cost_usd(usage, pricing),
        "pricing_snapshot_id": pricing["pricing_snapshot_id"],
        "prompt_sha256": prompt_sha256,
        "context_ids": context_ids,
        "role": "answer_generation",
    }


def _dump_optional_model(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return {key: _dump_optional_model(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_dump_optional_model(item) for item in value]
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump(exclude_none=True)
        except TypeError:
            dumped = model_dump()
        return _dump_optional_model(dumped)
    return value


def snapshot_api_response(response: Any) -> dict[str, Any]:
    """Keep billing and completion evidence when response processing fails."""
    usage = _dump_optional_model(getattr(response, "usage", None))
    return {
        "response_id": getattr(response, "id", None),
        "model": getattr(response, "model", None),
        "status": getattr(response, "status", None),
        "incomplete_details": _dump_optional_model(
            getattr(response, "incomplete_details", None)
        ),
        "api_error": _dump_optional_model(getattr(response, "error", None)),
        "usage": usage,
        "output": _dump_optional_model(getattr(response, "output", None)),
        "output_text_present": bool(getattr(response, "output_text", "")),
    }


def execute_one(
    experiment_record: dict[str, Any],
    config: dict[str, Any],
    *,
    client: Any,
    input_base_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute one request through an injected OpenAI client and validate the response."""
    request = build_openai_request(
        experiment_record, config, input_base_dir=input_base_dir
    )
    response = client.responses.create(**request)
    output_text = response.output_text
    try:
        parsed = json.loads(output_text)
    except (json.JSONDecodeError, TypeError) as error:
        raise ResponseProcessingError(
            "API response did not contain valid structured JSON output",
            response=response,
            cause=error,
        ) from error
    if not isinstance(parsed, dict):
        raise ValueError("structured model output must be a JSON object")
    supplied_pages = list(experiment_record.get("evidence_pages", []))
    usage = response.usage.model_dump() if response.usage is not None else None
    return {
        "schema_version": 1,
        "question_id": experiment_record.get("question_id"),
        "doc_id": experiment_record.get("doc_id"),
        "condition": experiment_record.get("condition"),
        "evidence_pages": supplied_pages,
        "model": response.model,
        "response_id": response.id,
        "output": parsed,
        "validation": validate_grounded_output(
            parsed,
            supplied_pages,
            allow_uncited_answer=experiment_record.get("condition") == "closed_book",
        ),
        "usage": usage,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--acknowledge-cost")
    args = parser.parse_args()

    experiment_record = _read_json_object(args.input)
    config = _read_json_object(args.config)
    request = build_openai_request(
        experiment_record, config, input_base_dir=args.input.parent
    )
    validate_execution_logging_config(config)
    pricing_path = args.config.parent / config["pricing_snapshot_path"]
    pricing = validate_pricing_snapshot(
        _read_json_object(pricing_path), expected_model=request["model"]
    )
    approved_hard_cap_usd = load_single_request_cap(config, config_path=args.config)

    if not args.execute:
        print(
            json.dumps(
                {
                    "mode": "dry_run",
                    "paid_request_sent": False,
                    "model": request["model"],
                    "question_id": experiment_record.get("question_id"),
                    "condition": experiment_record.get("condition"),
                    "evidence_pages": experiment_record.get("evidence_pages"),
                    "experiment_id": config["experiment_id"],
                    "max_retries": config["max_retries"],
                    "pricing_snapshot_id": pricing["pricing_snapshot_id"],
                    "approved_hard_cap_usd": approved_hard_cap_usd,
                    "budget_preflight": "performed immediately before paid generation",
                    "input_sha256": sha256_file(args.input),
                    "config_sha256": sha256_file(args.config),
                    "output": str(args.output),
                },
                indent=2,
            )
        )
        return

    if args.acknowledge_cost != COST_ACKNOWLEDGEMENT:
        raise RuntimeError("paid execution requires the exact cost acknowledgement")
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not configured")
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable response: {args.output}")
    try:
        from openai import OpenAI
    except ImportError as error:  # pragma: no cover - environment-specific
        raise RuntimeError("openai==3.7.0 is required for paid execution") from error

    client = OpenAI(max_retries=config["max_retries"])
    budget_preflight = preflight_request_budget(
        client,
        request,
        pricing,
        approved_hard_cap_usd=approved_hard_cap_usd,
    )
    print(
        "Budget preflight: "
        f"conservative maximum=${budget_preflight['conservative_cost_usd']:.6f}, "
        f"approved cap=${approved_hard_cap_usd:.2f}; proceeding."
    )

    request_date_utc = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    try:
        result = execute_one(
            experiment_record,
            config,
            client=client,
            input_base_dir=args.input.parent,
        )
    except Exception as error:
        latency_ms = (time.perf_counter() - started) * 1000
        api_response = (
            snapshot_api_response(error.api_response)
            if isinstance(error, ResponseProcessingError)
            else None
        )
        usage = None if api_response is None else api_response["usage"]
        model_snapshot = request["model"]
        if api_response is not None and api_response["model"]:
            model_snapshot = api_response["model"]
        call_log = build_call_log(
            experiment_record,
            config,
            request,
            pricing,
            model_snapshot=model_snapshot,
            usage=usage,
            request_date_utc=request_date_utc,
            latency_ms=latency_ms,
            status="error",
        )
        stamp = datetime.fromisoformat(request_date_utc).strftime("%Y%m%dT%H%M%S%fZ")
        failure_path = args.output.with_name(
            f"{args.output.stem}.failure-{stamp}{args.output.suffix}"
        )
        failure_record = {
            "schema_version": 1,
            "question_id": experiment_record.get("question_id"),
            "condition": experiment_record.get("condition"),
            "call_log": call_log,
            "api_response": api_response,
            "error": {
                "type": type(error).__name__,
                "status_code": getattr(error, "status_code", None),
                "cause_type": (
                    type(error.processing_cause).__name__
                    if isinstance(error, ResponseProcessingError)
                    else None
                ),
            },
        }
        write_json(failure_path, failure_record)
        raise RuntimeError(f"API attempt metadata written to {failure_path}") from error

    latency_ms = (time.perf_counter() - started) * 1000
    result["call_log"] = build_call_log(
        experiment_record,
        config,
        request,
        pricing,
        model_snapshot=result["model"],
        usage=result["usage"],
        request_date_utc=request_date_utc,
        latency_ms=latency_ms,
        status="ok",
    )
    result["budget_preflight"] = budget_preflight
    result["input_sha256"] = sha256_file(args.input)
    result["config_sha256"] = sha256_file(args.config)
    result["pricing_snapshot_sha256"] = sha256_file(pricing_path)
    result["request_sha256"] = hashlib.sha256(canonical_json_bytes(request)).hexdigest()
    write_json(args.output, result)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
