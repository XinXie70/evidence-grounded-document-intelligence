"""Offline preflight for the one-time locked test without opening its labels."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .constants import LOCKED_TEST_ACK, LOCKED_TEST_ENV
from .io import sha256_file
from .v1_system_freeze import verify_system_freeze


def _load_checksums(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        digest, relative = line.split("  ", 1)
        if len(digest) != 64 or relative in entries:
            raise ValueError("checksum manifest is invalid")
        entries[relative] = digest
    return entries


def run_preflight(
    *,
    root: Path,
    split_manifest: dict[str, Any],
    pdf_audit: dict[str, Any],
    threshold: dict[str, Any],
    environment: dict[str, Any],
    checksums_path: Path,
    freeze_manifest: dict[str, Any] | None = None,
    freeze_spec_path: Path | None = None,
    forbidden_artifacts: tuple[str, ...] = (),
) -> dict[str, Any]:
    if os.environ.get(LOCKED_TEST_ENV) == LOCKED_TEST_ACK:
        raise RuntimeError("locked-test access guard must remain disabled during preflight")
    locked = split_manifest.get("locked_test", {})
    tune = split_manifest.get("development_tune", {})
    calibration = split_manifest.get("development_calibration", {})
    locked_docs = locked.get("document_ids")
    if (
        locked.get("document_count") != 156
        or locked.get("question_count") != 730
        or not isinstance(locked_docs, list)
        or len(locked_docs) != 156
        or "question_ids" in locked
        or len(locked.get("question_ids_sha256", "")) != 64
    ):
        raise ValueError("locked-test split metadata is not sealed as expected")
    if set(locked_docs) & (set(tune.get("document_ids", [])) | set(calibration.get("document_ids", []))):
        raise ValueError("document leakage exists across evaluation splits")
    if (
        pdf_audit.get("observed_pdf_count") != 273
        or pdf_audit.get("openable_pdf_count") != 273
        or pdf_audit.get("total_pages") != 14014
        or any(not document.get("openable") for document in pdf_audit.get("documents", []))
    ):
        raise ValueError("PDF integrity audit is incomplete")
    if (
        threshold.get("status") != "protocol_corrected_and_frozen_before_locked_test"
        or threshold.get("locked_test_accessed") is not False
        or threshold.get("confidence_threshold") != 0.3566666666666667
    ):
        raise ValueError("final confidence threshold is not frozen")
    if (
        environment.get("status") != "recorded_before_locked_test"
        or environment.get("locked_test_accessed") is not False
    ):
        raise ValueError("environment snapshot does not preserve the pre-test boundary")
    existing = [relative for relative in forbidden_artifacts if (root / relative).exists()]
    if existing:
        raise ValueError(f"locked-test artifacts already exist: {existing}")

    checksums = _load_checksums(checksums_path)
    verified_pdfs = 0
    for doc_id in locked_docs:
        relative = f"data/raw/docscope/pdfs/{doc_id}.pdf"
        expected = checksums.get(relative)
        path = root / relative
        if expected is None or not path.is_file() or sha256_file(path) != expected:
            raise ValueError(f"locked-test PDF checksum failed: {doc_id}")
        verified_pdfs += 1
    freeze = None
    if freeze_manifest is not None:
        freeze = verify_system_freeze(
            freeze_manifest, root, spec_path=freeze_spec_path
        )
    return {
        "status": "ready_for_explicit_locked_test_authorization",
        "paid_api_called": False,
        "locked_test_accessed": False,
        "locked_document_count": len(locked_docs),
        "locked_question_count": locked["question_count"],
        "locked_pdf_checksums_verified": verified_pdfs,
        "all_dataset_pdfs_openable": pdf_audit["openable_pdf_count"],
        "all_dataset_pages_audited": pdf_audit["total_pages"],
        "confidence_threshold": threshold["confidence_threshold"],
        "system_freeze": freeze,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--split-manifest", required=True, type=Path)
    parser.add_argument("--pdf-audit", required=True, type=Path)
    parser.add_argument("--checksums", required=True, type=Path)
    parser.add_argument("--threshold", required=True, type=Path)
    parser.add_argument("--environment", required=True, type=Path)
    parser.add_argument("--freeze-manifest", type=Path)
    parser.add_argument("--freeze-spec", type=Path)
    parser.add_argument("--forbid", action="append", default=[])
    args = parser.parse_args()
    root = args.root.resolve()
    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    result = run_preflight(
        root=root,
        split_manifest=load(args.split_manifest),
        pdf_audit=load(args.pdf_audit),
        threshold=load(args.threshold),
        environment=load(args.environment),
        checksums_path=args.checksums,
        freeze_manifest=None if args.freeze_manifest is None else load(args.freeze_manifest),
        freeze_spec_path=args.freeze_spec,
        forbidden_artifacts=tuple(args.forbid),
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
