"""Create deterministic, page-bounded JSONL corpora from PDFs."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Iterable
from pathlib import Path

from .text import PageRecord, build_page_record


def extract_pdf_page_records(pdf_path: Path, doc_id: str) -> list[PageRecord]:
    """Extract every physical PDF page in 1-based order.

    Extraction errors fail loudly instead of being silently labelled as missing text.
    """
    try:
        from pypdf import PdfReader
    except ImportError as error:  # pragma: no cover - environment-specific message
        raise RuntimeError("pypdf is required to extract PDF page records") from error

    reader = PdfReader(str(pdf_path), strict=False)
    records: list[PageRecord] = []
    for page_number, pdf_page in enumerate(reader.pages, start=1):
        try:
            raw_text = pdf_page.extract_text() or ""
        except Exception as error:
            raise RuntimeError(
                f"text extraction failed for doc_id={doc_id}, page={page_number}"
            ) from error
        records.append(build_page_record(doc_id, page_number, raw_text))
    return records


def write_page_records_jsonl(path: Path, records: Iterable[PageRecord]) -> int:
    """Write one PageRecord per line using an atomic local replacement."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    count = 0
    with temporary.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.to_dict(), sort_keys=True, ensure_ascii=False) + "\n")
            count += 1
    os.replace(temporary, path)
    return count


def read_page_records_jsonl(path: Path) -> list[PageRecord]:
    """Reload a PageRecord JSONL file for verification or indexing."""
    records: list[PageRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise ValueError(f"blank JSONL line at {line_number}")
            payload = json.loads(line)
            records.append(PageRecord(**payload))
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--doc-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    records = extract_pdf_page_records(args.pdf, args.doc_id)
    written = write_page_records_jsonl(args.output, records)
    reloaded = read_page_records_jsonl(args.output)
    if reloaded != records:
        raise RuntimeError("JSONL round-trip verification failed")
    print(
        json.dumps(
            {
                "doc_id": args.doc_id,
                "output": str(args.output),
                "page_records_written": written,
                "status_counts": {
                    status: sum(record.extraction_status == status for record in records)
                    for status in ("ok", "low_text", "text_layer_missing")
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
