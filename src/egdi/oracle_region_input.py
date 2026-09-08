"""Build a no-answer-leakage C3 Oracle Region input from reviewed crops."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .io import sha256_file, write_json


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def build_oracle_region_record(
    oracle_page_record: dict[str, Any],
    crop_manifest: dict[str, Any],
    manual_review: dict[str, Any],
) -> dict[str, Any]:
    """Create one C3 input while deliberately excluding gold answers and facts."""
    question_id = oracle_page_record.get("question_id")
    condition = crop_manifest.get("condition", "oracle_region")
    if condition not in {"oracle_region", "oracle_region_context"}:
        raise ValueError("crop manifest condition must be an Oracle Region condition")
    if oracle_page_record.get("condition") != "oracle_page":
        raise ValueError("source input must be an oracle_page record")
    if crop_manifest.get("question_id") != question_id:
        raise ValueError("crop manifest question_id does not match source input")
    if manual_review.get("question_id") != question_id:
        raise ValueError("manual review question_id does not match source input")
    if manual_review.get("status") != "confirmed":
        raise ValueError("crop must be manually confirmed before C3 input construction")
    model_input = oracle_page_record.get("model_input")
    crops = crop_manifest.get("crops")
    if not isinstance(model_input, dict) or not isinstance(crops, list) or not crops:
        raise ValueError("source model_input and crop manifest crops are required")
    source_evidence = model_input.get("evidence")
    if not isinstance(source_evidence, list):
        raise ValueError("source model_input.evidence must be a list")
    text_by_page = {item.get("page"): item.get("text") for item in source_evidence}

    evidence: list[dict[str, Any]] = []
    regions: list[dict[str, Any]] = []
    for crop in crops:
        page = crop.get("page")
        native_page_text = text_by_page.get(page)
        if not isinstance(native_page_text, str):
            raise ValueError(f"source Oracle Page text is missing for page {page}")
        intersecting_text = ""
        text_scope = crop.get("text_scope")
        if native_page_text.strip():
            if text_scope == "crop_intersection":
                intersecting_text = crop.get("intersecting_text")
                if not isinstance(intersecting_text, str):
                    raise ValueError(
                        "crop-intersection evidence requires intersecting_text"
                    )
            elif text_scope == "image_only":
                if crop.get("intersecting_text") not in {None, ""}:
                    raise ValueError("image-only evidence cannot include native text")
            else:
                raise ValueError(
                    "non-empty pages require bbox-intersection or explicit image-only scope before C3 use"
                )
        elif text_scope is None:
            text_scope = "native_text_unavailable"
        image_path = crop.get("output_png")
        image_sha256 = crop.get("output_png_sha256")
        if not isinstance(image_path, str) or not image_path:
            raise ValueError("crop output_png must be a non-empty string")
        if not isinstance(image_sha256, str) or len(image_sha256) != 64:
            raise ValueError("crop output_png_sha256 must be a SHA-256 hex string")
        evidence.append(
            {
                "page": page,
                "evidence_local_id": crop.get("evidence_local_id"),
                "bbox": crop.get("bbox"),
                "text": intersecting_text,
                "text_scope": text_scope,
                "image_path": image_path,
                "image_sha256": image_sha256,
            }
        )
        regions.append(
            {
                "page": page,
                "evidence_local_id": crop.get("evidence_local_id"),
                "bbox": crop.get("bbox"),
                "element_type": crop.get("element_type"),
                "image_sha256": image_sha256,
            }
        )

    supplied_pages = list(dict.fromkeys(item["page"] for item in evidence))
    return {
        "schema_version": 1,
        "question_id": question_id,
        "doc_id": oracle_page_record.get("doc_id"),
        "condition": condition,
        "evidence_pages": supplied_pages,
        "evidence_regions": regions,
        "model_input": {
            "instructions": model_input.get("instructions"),
            "question": model_input.get("question"),
            "evidence": evidence,
            "response_schema": model_input.get("response_schema"),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oracle-page-input", required=True, type=Path)
    parser.add_argument("--crop-manifest", required=True, type=Path)
    parser.add_argument("--manual-review", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable input: {args.output}")
    record = build_oracle_region_record(
        _read_object(args.oracle_page_input),
        _read_object(args.crop_manifest),
        _read_object(args.manual_review),
    )
    write_json(args.output, record)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "question_id": record["question_id"],
                "condition": record["condition"],
                "evidence_region_count": len(record["evidence_regions"]),
                "output_sha256": sha256_file(args.output),
                "paid_request_sent": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
