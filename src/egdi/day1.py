"""Download and execute the frozen Day 1 data audit."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .access import load_for_day1_integrity_audit
from .constants import (
    ANSWERABLE_ZERO_EVIDENCE_ID,
    DATASET_REPO,
    DATASET_REVISION,
    OFFICIAL_CODE_REVISION,
    PROTOCOL_DATE,
)
from .io import sha256_file, write_json
from .splits import build_split_manifest

try:
    import requests
except ImportError:  # pragma: no cover - actionable CLI error
    requests = None


def _download_one(relative_path: str, raw_dir: Path) -> tuple[str, int]:
    if requests is None:
        raise RuntimeError("requests is required; install the pinned project dependencies")
    destination = raw_dir / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        return relative_path, destination.stat().st_size
    url = (
        f"https://huggingface.co/datasets/{DATASET_REPO}/resolve/"
        f"{DATASET_REVISION}/{quote(relative_path, safe='/')}?download=true"
    )
    temporary = destination.with_suffix(destination.suffix + ".part")
    with requests.get(url, stream=True, timeout=(30, 180)) as response:
        response.raise_for_status()
        with temporary.open("wb") as handle:
            for chunk in response.iter_content(1024 * 1024):
                if chunk:
                    handle.write(chunk)
    os.replace(temporary, destination)
    return relative_path, destination.stat().st_size


def download(raw_dir: Path, workers: int = 8) -> None:
    _download_one("benchmark.json", raw_dir)
    _download_one("NOTICE.md", raw_dir)
    records = load_for_day1_integrity_audit(raw_dir / "benchmark.json")
    doc_ids = sorted({record["pdf"]["doc_id_str"] for record in records})
    paths = [f"pdfs/{doc_id}.pdf" for doc_id in doc_ids]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_download_one, path, raw_dir) for path in paths]
        for index, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            path, size = future.result()
            if index % 25 == 0 or index == len(paths):
                print(f"downloaded/verified {index}/{len(paths)} PDFs; latest={path} ({size} bytes)")


def _audit_pdf(path: Path, pdfinfo: str, python_executable: str) -> dict[str, Any]:
    info = subprocess.run(
        [pdfinfo, str(path)], capture_output=True, text=True, timeout=60, check=False
    )
    metadata: dict[str, str] = {}
    for line in info.stdout.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()
    result: dict[str, Any] = {
        "doc_id": path.stem,
        "file_size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "pdfinfo_exit_code": info.returncode,
        "openable": info.returncode == 0 and "Pages" in metadata,
        "encrypted": metadata.get("Encrypted", "unknown"),
        "page_count": int(metadata["Pages"]) if metadata.get("Pages", "").isdigit() else None,
    }
    if not result["openable"]:
        result["error"] = info.stderr.strip()[:500]
        return result

    extractor = (
        "import json,sys; from pypdf import PdfReader; r=PdfReader(sys.argv[1], strict=False); "
        "out=[]; "
        "[(lambda n: out.append({'page':i+1,'chars':n,'text_layer_missing':n<20,"
        "'low_text':n<100,'extract_error':None}))(len(''.join((p.extract_text() or '').split()))) "
        "for i,p in enumerate(r.pages)]; print(json.dumps(out))"
    )
    extracted = subprocess.run(
        [python_executable, "-c", extractor, str(path)],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if extracted.returncode != 0:
        result["text_extraction_error"] = extracted.stderr.strip()[-1000:]
        result["pages"] = []
    else:
        result["pages"] = json.loads(extracted.stdout)
    return result


def audit(root: Path, pdfinfo: str, python_executable: str, workers: int = 4) -> None:
    raw_dir = root / "data" / "raw" / "docscope"
    benchmark_path = raw_dir / "benchmark.json"
    records = load_for_day1_integrity_audit(benchmark_path)
    doc_ids = sorted({record["pdf"]["doc_id_str"] for record in records})
    pdf_paths = [raw_dir / "pdfs" / f"{doc_id}.pdf" for doc_id in doc_ids]
    missing = [str(path) for path in pdf_paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"missing {len(missing)} PDFs; run download first")

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        pdf_results = list(pool.map(lambda p: _audit_pdf(p, pdfinfo, python_executable), pdf_paths))
    pdf_results.sort(key=lambda item: item["doc_id"])

    evidence_page_errors: list[dict[str, Any]] = []
    page_counts = {item["doc_id"]: item["page_count"] for item in pdf_results}
    for record in records:
        doc_id = record["pdf"]["doc_id_str"]
        for evidence in record.get("evidences", []):
            if not 1 <= evidence["page"] <= page_counts[doc_id]:
                evidence_page_errors.append(
                    {"question_id": record["id"], "doc_id": doc_id, "page": evidence["page"]}
                )

    all_pages = [page for item in pdf_results for page in item.get("pages", [])]
    no_text = [page for page in all_pages if page["chars"] < 20]
    low_text = [page for page in all_pages if page["chars"] < 100]
    extraction_failures = [item["doc_id"] for item in pdf_results if "text_extraction_error" in item]
    pdf_audit = {
        "schema_version": 1,
        "dataset_revision": DATASET_REVISION,
        "audit_date": PROTOCOL_DATE,
        "expected_pdf_count": len(doc_ids),
        "observed_pdf_count": len(pdf_results),
        "openable_pdf_count": sum(item["openable"] for item in pdf_results),
        "encrypted_pdf_count": sum(str(item["encrypted"]).lower().startswith("yes") for item in pdf_results),
        "total_pages": sum(item["page_count"] or 0 for item in pdf_results),
        "evidence_page_range_error_count": len(evidence_page_errors),
        "evidence_page_range_errors": evidence_page_errors,
        "documents": pdf_results,
    }
    write_json(root / "data" / "manifests" / "pdf_audit.json", pdf_audit)

    text_audit = {
        "schema_version": 1,
        "parser": "pypdf 6.10.0 PdfReader(strict=False).pages[].extract_text()",
        "character_measure": "non-whitespace Unicode code points",
        "thresholds": {"text_layer_missing": "<20 chars/page", "low_text": "<100 chars/page"},
        "total_pages": len(all_pages),
        "text_layer_missing_pages": len(no_text),
        "low_text_pages": len(low_text),
        "text_layer_missing_rate": len(no_text) / len(all_pages),
        "low_text_rate": len(low_text) / len(all_pages),
        "document_extraction_failure_count": len(extraction_failures),
        "document_extraction_failures": extraction_failures,
        "per_document": [
            {
                "doc_id": item["doc_id"],
                "page_count": len(item.get("pages", [])),
                "text_layer_missing_pages": sum(p["chars"] < 20 for p in item.get("pages", [])),
                "low_text_pages": sum(p["chars"] < 100 for p in item.get("pages", [])),
                "total_non_whitespace_chars": sum(p["chars"] for p in item.get("pages", [])),
            }
            for item in pdf_results
        ],
    }
    page_lookup = {
        (item["doc_id"], page["page"]): page
        for item in pdf_results
        for page in item.get("pages", [])
    }
    gold_page_keys = {
        (record["pdf"]["doc_id_str"], evidence["page"])
        for record in records
        for evidence in record.get("evidences", [])
    }
    impacted_missing_questions = {
        record["id"]
        for record in records
        if any(
            page_lookup[(record["pdf"]["doc_id_str"], evidence["page"])]["text_layer_missing"]
            for evidence in record.get("evidences", [])
        )
    }
    impacted_low_questions = {
        record["id"]
        for record in records
        if any(
            page_lookup[(record["pdf"]["doc_id_str"], evidence["page"])]["low_text"]
            for evidence in record.get("evidences", [])
        )
    }
    text_audit["gold_evidence_pages"] = {
        "unique_page_count": len(gold_page_keys),
        "text_layer_missing_pages": sum(page_lookup[key]["text_layer_missing"] for key in gold_page_keys),
        "low_text_pages": sum(page_lookup[key]["low_text"] for key in gold_page_keys),
        "questions_with_any_missing_text_evidence_page": len(impacted_missing_questions),
        "questions_with_any_low_text_evidence_page": len(impacted_low_questions),
    }
    write_json(root / "data" / "manifests" / "text_layer_audit.json", text_audit)

    question_ids = [record["id"] for record in records]
    malformed_bboxes: list[dict[str, Any]] = []
    orphan_fact_links: list[dict[str, Any]] = []
    for record in records:
        evidence_ids = {evidence.get("local_id") for evidence in record.get("evidences", [])}
        for evidence in record.get("evidences", []):
            bbox = evidence.get("bbox")
            valid = (
                isinstance(bbox, list)
                and len(bbox) == 4
                and all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in bbox)
                and bbox[2] > bbox[0]
                and bbox[3] > bbox[1]
            )
            if not valid:
                malformed_bboxes.append(
                    {"question_id": record["id"], "evidence_local_id": evidence.get("local_id")}
                )
        for fact in record.get("facts", []):
            if fact.get("evidence_local_id") not in evidence_ids:
                orphan_fact_links.append(
                    {"question_id": record["id"], "fact_local_id": fact.get("local_id")}
                )
    write_json(
        root / "data" / "manifests" / "annotation_audit.json",
        {
            "schema_version": 1,
            "question_count": len(records),
            "duplicate_question_id_count": len(question_ids) - len(set(question_ids)),
            "evidence_region_count": sum(len(record.get("evidences", [])) for record in records),
            "fact_count": sum(len(record.get("facts", [])) for record in records),
            "malformed_bbox_count": len(malformed_bboxes),
            "malformed_bboxes": malformed_bboxes,
            "orphan_fact_link_count": len(orphan_fact_links),
            "orphan_fact_links": orphan_fact_links,
            "evidence_page_range_error_count": len(evidence_page_errors),
        },
    )

    split_manifest = build_split_manifest(records)
    write_json(root / "data" / "manifests" / "split_manifest.json", split_manifest)

    anomaly = next(record for record in records if record["id"] == ANSWERABLE_ZERO_EVIDENCE_ID)
    zero_evidence = [record for record in records if not record.get("evidences")]
    write_json(
        root / "data" / "manifests" / "anomaly_resolution.json",
        {
            "schema_version": 1,
            "zero_evidence_record_count": len(zero_evidence),
            "zero_evidence_question_ids": sorted(record["id"] for record in zero_evidence),
            "answerable_zero_evidence": {
                "question_id": anomaly["id"],
                "observed_answer": anomaly["answer"]["answer_text"],
                "decision": "exclude_from_evidence_retrieval_metrics",
                "answer_metrics": "retain_with_audit_flag_and_report_sensitivity_with_and_without",
                "reason": "released answerable record has no gold evidence",
            },
        },
    )

    checksums = [("data/raw/docscope/benchmark.json", sha256_file(benchmark_path))]
    checksums.extend(
        (f"data/raw/docscope/pdfs/{item['doc_id']}.pdf", item["sha256"]) for item in pdf_results
    )
    split_path = root / "data" / "manifests" / "split_manifest.json"
    checksums.append(("data/manifests/split_manifest.json", sha256_file(split_path)))
    checksum_text = "".join(f"{digest}  {path}\n" for path, digest in sorted(checksums))
    (root / "data" / "manifests" / "checksums.sha256").write_text(checksum_text, encoding="utf-8")

    observed = Counter(record["split"] for record in records)
    write_json(
        root / "data" / "manifests" / "source.json",
        {
            "schema_version": 1,
            "dataset": "DocScope",
            "repository": DATASET_REPO,
            "repository_type": "dataset",
            "revision": DATASET_REVISION,
            "official_code": {
                "repository": "https://github.com/MiliLab/DocScope",
                "revision": OFFICIAL_CODE_REVISION,
            },
            "canonical_url": f"https://huggingface.co/datasets/{DATASET_REPO}/tree/{DATASET_REVISION}",
            "pinned_on": PROTOCOL_DATE,
            "annotation_file": "benchmark.json",
            "notice_sha256": sha256_file(raw_dir / "NOTICE.md"),
            "pdf_directory": "pdfs/",
            "observed": {"questions": len(records), "pdfs": len(doc_ids), "splits": dict(observed)},
            "licence": {
                "annotations": "CC BY-NC-SA 4.0",
                "pdf_collection_source": "FinePDFs / ODC-By 1.0",
                "note": "Individual PDFs retain source copyright; non-commercial research use; do not redistribute.",
            },
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("download", "audit", "all"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--pdfinfo", default="pdfinfo")
    parser.add_argument("--extract-python", default=sys.executable)
    args = parser.parse_args()
    raw_dir = args.root / "data" / "raw" / "docscope"
    if args.command in {"download", "all"}:
        download(raw_dir, workers=max(args.workers, 1))
    if args.command in {"audit", "all"}:
        audit(args.root, args.pdfinfo, args.extract_python, workers=max(args.workers, 1))


if __name__ == "__main__":
    main()
