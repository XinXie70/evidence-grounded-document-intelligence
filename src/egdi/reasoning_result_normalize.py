"""Create canonical validation-ready copies of immutable reasoning results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .io import sha256_file, write_json
from .reasoning_api import canonicalize_grounded_output, validate_grounded_output


def normalize_result(result: dict[str, Any]) -> dict[str, Any]:
    """Normalize an answer result without changing answerability or answer text."""
    output = result.get("output")
    evidence_pages = result.get("evidence_pages")
    if not isinstance(output, dict) or not isinstance(evidence_pages, list):
        raise ValueError("reasoning result is malformed")
    normalized_output, transformations = canonicalize_grounded_output(output)
    existing = result.get("output_normalization", {})
    existing_transformations = existing.get("transformations", [])
    if not isinstance(existing_transformations, list) or any(
        not isinstance(item, str) for item in existing_transformations
    ):
        raise ValueError("existing output normalization metadata is malformed")
    transformations = list(dict.fromkeys([*existing_transformations, *transformations]))
    normalized = dict(result)
    normalized["output"] = normalized_output
    normalized["validation"] = validate_grounded_output(
        normalized_output,
        evidence_pages,
        allow_uncited_answer=result.get("condition") == "closed_book",
    )
    normalized["output_normalization"] = {
        "applied": bool(transformations),
        "transformations": transformations,
    }
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    normalized_count = 0
    invalid: list[str] = []
    for case in manifest.get("cases", []):
        pilot_id = case["pilot_id"]
        source = args.source_dir / pilot_id / "real_retrieval.json"
        target = args.output_dir / pilot_id / "real_retrieval.json"
        if target.exists():
            raise FileExistsError(f"refusing to overwrite normalized result: {target}")
        result = json.loads(source.read_text(encoding="utf-8"))
        if result.get("question_id") != case["question_id"]:
            raise ValueError(f"result identity mismatch: {source}")
        normalized = normalize_result(result)
        normalized["source_result_sha256"] = sha256_file(source)
        if normalized["output_normalization"]["applied"]:
            normalized_count += 1
        if not normalized["validation"]["valid"]:
            invalid.append(pilot_id)
        write_json(target, normalized)
    summary = {
        "schema_version": 1,
        "source_manifest_sha256": sha256_file(args.manifest),
        "case_count": len(manifest.get("cases", [])),
        "normalized_case_count": normalized_count,
        "invalid_case_ids": invalid,
        "status": "complete" if not invalid else "complete_with_invalid_outputs",
    }
    batch_id = manifest.get("batch_id")
    summary_name = (
        f"normalization_summary_{batch_id}.json"
        if isinstance(batch_id, str) and batch_id
        else "normalization_summary.json"
    )
    write_json(args.output_dir / summary_name, summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
