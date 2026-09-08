"""Build an auditable OCR corpus with selected page-orientation recoveries."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, Sequence

from .corpus import read_page_records_jsonl, write_page_records_jsonl
from .evidence_package import load_layout_texts
from .io import sha256_file, write_json
from .ocr_orientation import CARDINAL_ROTATIONS
from .text import build_page_record


def build_orientation_recovered_corpus(
    baseline_corpus: Path,
    baseline_text_dir: Path,
    recoveries: Sequence[dict[str, Any]],
    output_dir: Path,
) -> dict[str, Any]:
    """Copy a baseline OCR corpus and replace only independently selected pages."""
    if not baseline_corpus.is_file():
        raise FileNotFoundError(f"baseline corpus does not exist: {baseline_corpus}")
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite recovered corpus: {output_dir}")
    staging_dir = output_dir.with_name(output_dir.name + ".partial")
    if staging_dir.exists():
        raise FileExistsError(f"unfinished recovered corpus exists: {staging_dir}")
    if not recoveries:
        raise ValueError("at least one orientation recovery is required")

    records = read_page_records_jsonl(baseline_corpus)
    if not records:
        raise ValueError("baseline corpus must not be empty")
    doc_ids = {record.doc_id for record in records}
    pages = [record.page for record in records]
    if len(doc_ids) != 1 or pages != list(range(1, len(records) + 1)):
        raise ValueError("baseline corpus must contain one sequential document")
    doc_id = records[0].doc_id
    _, baseline_text_audit = load_layout_texts(baseline_text_dir, pages)

    recovery_by_page: dict[int, dict[str, Any]] = {}
    recovery_audit: list[dict[str, Any]] = []
    for recovery in recoveries:
        page = recovery.get("page")
        if isinstance(page, bool) or not isinstance(page, int) or page not in pages:
            raise ValueError("recovery page must exist in the baseline corpus")
        if page in recovery_by_page:
            raise ValueError(f"duplicate orientation recovery for page {page}")
        text_path = Path(recovery["text_path"])
        selection_path = Path(recovery["selection_path"])
        if not text_path.is_file():
            raise FileNotFoundError(f"recovered OCR text does not exist: {text_path}")
        if not selection_path.is_file():
            raise FileNotFoundError(
                f"orientation selection does not exist: {selection_path}"
            )
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
        if selection.get("uses_gold_or_answer_labels") is not False:
            raise ValueError("orientation selection must explicitly be label-free")
        rotation = selection.get("selected_rotation_degrees_clockwise")
        if rotation not in CARDINAL_ROTATIONS:
            raise ValueError("orientation selection has an invalid rotation")
        recovery_by_page[page] = {
            "text_path": text_path,
            "selection_path": selection_path,
            "rotation": rotation,
        }
        recovery_audit.append(
            {
                "page": page,
                "selected_rotation_degrees_clockwise": rotation,
                "source_text_path": str(text_path),
                "source_text_sha256": sha256_file(text_path),
                "selection_path": str(selection_path),
                "selection_sha256": sha256_file(selection_path),
            }
        )

    text_dir = staging_dir / "text"
    text_dir.mkdir(parents=True)
    baseline_path_by_page = {
        item["page"]: Path(item["path"]) for item in baseline_text_audit
    }
    derived_records = []
    page_audit: list[dict[str, Any]] = []
    for record in records:
        page = record.page
        source_path = baseline_path_by_page[page]
        source_kind = "baseline"
        rotation = 0
        if page in recovery_by_page:
            source_path = recovery_by_page[page]["text_path"]
            source_kind = "orientation_recovery"
            rotation = recovery_by_page[page]["rotation"]
        destination = text_dir / f"page-{page:04d}.txt"
        shutil.copy2(source_path, destination)
        raw_text = destination.read_text(encoding="utf-8")
        derived_records.append(build_page_record(doc_id, page, raw_text))
        page_audit.append(
            {
                "page": page,
                "source_kind": source_kind,
                "rotation_degrees_clockwise": rotation,
                "text_path": str(destination.relative_to(staging_dir)),
                "text_sha256": sha256_file(destination),
            }
        )

    corpus_path = staging_dir / "page_records.jsonl"
    write_page_records_jsonl(corpus_path, derived_records)
    if read_page_records_jsonl(corpus_path) != derived_records:
        raise RuntimeError("recovered OCR corpus round-trip verification failed")
    changed_pages = [
        record.page
        for record, derived in zip(records, derived_records, strict=True)
        if record != derived
    ]
    expected_pages = sorted(recovery_by_page)
    if changed_pages != expected_pages:
        raise RuntimeError(
            f"changed pages {changed_pages} do not match recoveries {expected_pages}"
        )

    manifest = {
        "schema_version": 1,
        "doc_id": doc_id,
        "page_count": len(records),
        "baseline": {
            "corpus_path": str(baseline_corpus),
            "corpus_sha256": sha256_file(baseline_corpus),
            "layout_text_dir": str(baseline_text_dir),
        },
        "recoveries": recovery_audit,
        "changed_pages": changed_pages,
        "page_records": {
            "path": "page_records.jsonl",
            "sha256": sha256_file(corpus_path),
            "record_count": len(derived_records),
        },
        "layout_text_dir": "text",
        "pages": page_audit,
        "uses_gold_or_answer_labels": False,
    }
    write_json(staging_dir / "manifest.json", manifest)
    staging_dir.replace(output_dir)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-corpus", required=True, type=Path)
    parser.add_argument("--baseline-text-dir", required=True, type=Path)
    parser.add_argument("--recovery-spec", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    spec = json.loads(args.recovery_spec.read_text(encoding="utf-8"))
    manifest = build_orientation_recovered_corpus(
        args.baseline_corpus,
        args.baseline_text_dir,
        spec["recoveries"],
        args.output_dir,
    )
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir),
                "manifest_sha256": sha256_file(args.output_dir / "manifest.json"),
                "corpus_sha256": manifest["page_records"]["sha256"],
                "changed_pages": manifest["changed_pages"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
