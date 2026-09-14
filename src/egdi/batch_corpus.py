"""Safely plan and build Page Record JSONL files for an unlocked development split."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

from .access import require_evaluation_split_access
from .corpus import (
    extract_pdf_page_records,
    read_page_records_jsonl,
    write_page_records_jsonl,
)
from .io import sha256_file, write_json


@dataclass(frozen=True)
class BatchDocumentPlan:
    doc_id: str
    expected_pages: int
    source_pdf: Path
    source_sha256: str
    output_jsonl: Path
    status: str

    def to_dict(self) -> dict[str, str | int]:
        payload = asdict(self)
        payload["source_pdf"] = str(self.source_pdf)
        payload["output_jsonl"] = str(self.output_jsonl)
        return payload


def _read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _validate_existing_output(plan: BatchDocumentPlan) -> None:
    records = read_page_records_jsonl(plan.output_jsonl)
    if len(records) != plan.expected_pages:
        raise ValueError(
            f"existing output page count mismatch for {plan.doc_id}: "
            f"expected {plan.expected_pages}, found {len(records)}"
        )
    if any(record.doc_id != plan.doc_id for record in records):
        raise ValueError(f"existing output contains a different doc_id: {plan.doc_id}")
    if [record.page for record in records] != list(range(1, plan.expected_pages + 1)):
        raise ValueError(f"existing output pages are not sequential for {plan.doc_id}")


ALLOWED_SPLITS = {"development_tune", "development_calibration", "locked_test"}


def plan_document_split(
    split_manifest_path: Path,
    pdf_audit_path: Path,
    pdf_dir: Path,
    output_dir: Path,
    split_name: str,
    requested_doc_ids: Sequence[str] | None = None,
) -> list[BatchDocumentPlan]:
    """Build a validated, non-writing plan for one guarded evaluation split."""
    if split_name not in ALLOWED_SPLITS:
        raise ValueError("unknown evaluation split")
    require_evaluation_split_access(split_name)
    split_manifest = _read_json_object(split_manifest_path)
    target_section = split_manifest.get(split_name)
    if not isinstance(target_section, dict):
        raise ValueError(f"split manifest is missing {split_name}")
    target_ids = target_section.get("document_ids")
    if not isinstance(target_ids, list) or not all(isinstance(value, str) for value in target_ids):
        raise ValueError(f"{split_name}.document_ids must be a list of strings")
    if len(target_ids) != len(set(target_ids)):
        raise ValueError(f"{split_name} contains duplicate document IDs")
    if target_section.get("document_count") != len(target_ids):
        raise ValueError(f"{split_name} document_count does not match document_ids")

    allowed = set(target_ids)
    forbidden: dict[str, str] = {}
    for other_split in ({"development_tune", "development_calibration", "locked_test"} - {split_name}):
        section = split_manifest.get(other_split)
        if not isinstance(section, dict) or not isinstance(section.get("document_ids"), list):
            raise ValueError(f"split manifest is missing {other_split}.document_ids")
        for doc_id in section["document_ids"]:
            forbidden[doc_id] = other_split
    if allowed & set(forbidden):
        raise ValueError(f"{split_name} overlaps another split")

    if requested_doc_ids is None:
        selected = sorted(allowed)
    else:
        if len(requested_doc_ids) != len(set(requested_doc_ids)):
            raise ValueError("requested document IDs must be unique")
        rejected = [doc_id for doc_id in requested_doc_ids if doc_id not in allowed]
        if rejected:
            details = [f"{doc_id} ({forbidden.get(doc_id, 'unknown')})" for doc_id in rejected]
            raise ValueError(f"requested documents are not {split_name}: " + ", ".join(details))
        selected = sorted(requested_doc_ids)

    pdf_audit = _read_json_object(pdf_audit_path)
    audit_documents = pdf_audit.get("documents")
    if not isinstance(audit_documents, list):
        raise ValueError("PDF audit is missing documents")
    audit_by_id: dict[str, dict[str, Any]] = {}
    for document in audit_documents:
        if not isinstance(document, dict) or not isinstance(document.get("doc_id"), str):
            raise ValueError("PDF audit contains an invalid document record")
        doc_id = document["doc_id"]
        if doc_id in audit_by_id:
            raise ValueError(f"PDF audit contains duplicate doc_id: {doc_id}")
        audit_by_id[doc_id] = document

    plans: list[BatchDocumentPlan] = []
    for doc_id in selected:
        audit = audit_by_id.get(doc_id)
        if audit is None:
            raise ValueError(f"PDF audit is missing {split_name} document: {doc_id}")
        expected_pages = audit.get("page_count")
        if isinstance(expected_pages, bool) or not isinstance(expected_pages, int) or expected_pages < 1:
            raise ValueError(f"invalid audited page count for {doc_id}")
        if audit.get("openable") is not True:
            raise ValueError(f"source PDF is not audited as openable: {doc_id}")
        source_sha256 = audit.get("sha256")
        if not isinstance(source_sha256, str) or len(source_sha256) != 64:
            raise ValueError(f"invalid audited SHA-256 for {doc_id}")
        source_pdf = pdf_dir / f"{doc_id}.pdf"
        if not source_pdf.is_file():
            raise FileNotFoundError(f"source PDF is missing: {source_pdf}")
        output_jsonl = output_dir / f"{doc_id}.jsonl"
        status = "verified_existing" if output_jsonl.exists() else "pending"
        plan = BatchDocumentPlan(
            doc_id=doc_id,
            expected_pages=expected_pages,
            source_pdf=source_pdf,
            source_sha256=source_sha256,
            output_jsonl=output_jsonl,
            status=status,
        )
        if status == "verified_existing":
            _validate_existing_output(plan)
        plans.append(plan)
    return plans


def plan_development_tune(
    split_manifest_path: Path,
    pdf_audit_path: Path,
    pdf_dir: Path,
    output_dir: Path,
    requested_doc_ids: Sequence[str] | None = None,
) -> list[BatchDocumentPlan]:
    """Backward-compatible development-tune planner."""
    return plan_document_split(
        split_manifest_path,
        pdf_audit_path,
        pdf_dir,
        output_dir,
        "development_tune",
        requested_doc_ids,
    )


def summarize_plan(
    plans: Sequence[BatchDocumentPlan], *, split_name: str = "development_tune"
) -> dict[str, Any]:
    if not plans:
        raise ValueError("batch plan cannot be empty")
    return {
        "mode": "dry_run",
        "split": split_name,
        "document_count": len(plans),
        "expected_page_records": sum(plan.expected_pages for plan in plans),
        "verified_existing_documents": sum(
            plan.status == "verified_existing" for plan in plans
        ),
        "pending_documents": sum(plan.status == "pending" for plan in plans),
        "documents": [plan.to_dict() for plan in plans],
    }


def execute_plan(
    plans: Sequence[BatchDocumentPlan], *, split_name: str = "development_tune"
) -> dict[str, Any]:
    """Generate only pending outputs, verify all outputs, and return a manifest."""
    if not plans:
        raise ValueError("batch plan cannot be empty")
    documents: list[dict[str, Any]] = []
    aggregate_status = {"ok": 0, "low_text": 0, "text_layer_missing": 0}
    generated = 0

    for plan in plans:
        actual_source_sha256 = sha256_file(plan.source_pdf)
        if actual_source_sha256 != plan.source_sha256:
            raise ValueError(f"source PDF checksum mismatch for {plan.doc_id}")
        if plan.status == "pending":
            records = extract_pdf_page_records(plan.source_pdf, plan.doc_id)
            if len(records) != plan.expected_pages:
                raise ValueError(
                    f"extracted page count mismatch for {plan.doc_id}: "
                    f"expected {plan.expected_pages}, found {len(records)}"
                )
            write_page_records_jsonl(plan.output_jsonl, records)
            generated += 1
        _validate_existing_output(plan)
        records = read_page_records_jsonl(plan.output_jsonl)
        status_counts = {
            status: sum(record.extraction_status == status for record in records)
            for status in aggregate_status
        }
        for status, count in status_counts.items():
            aggregate_status[status] += count
        documents.append(
            {
                "doc_id": plan.doc_id,
                "page_count": plan.expected_pages,
                "source_pdf_sha256": plan.source_sha256,
                "output_jsonl_sha256": sha256_file(plan.output_jsonl),
                "status_counts": status_counts,
            }
        )

    return {
        "schema_version": "egdi.page-record-batch.v1",
        "split": split_name,
        "document_count": len(plans),
        "page_record_count": sum(plan.expected_pages for plan in plans),
        "generated_documents": generated,
        "verified_existing_documents": len(plans) - generated,
        "status_counts": aggregate_status,
        "documents": documents,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split-manifest", required=True, type=Path)
    parser.add_argument("--pdf-audit", required=True, type=Path)
    parser.add_argument("--pdf-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--split",
        choices=sorted(ALLOWED_SPLITS),
        default="development_tune",
    )
    parser.add_argument("--doc-id", action="append", dest="doc_ids")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--manifest-output", type=Path)
    args = parser.parse_args()

    plans = plan_document_split(
        args.split_manifest,
        args.pdf_audit,
        args.pdf_dir,
        args.output_dir,
        args.split,
        requested_doc_ids=args.doc_ids,
    )
    if not args.execute:
        print(json.dumps(summarize_plan(plans, split_name=args.split), indent=2))
        return
    if args.manifest_output is None:
        parser.error("--manifest-output is required with --execute")
    manifest = execute_plan(plans, split_name=args.split)
    write_json(args.manifest_output, manifest)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
