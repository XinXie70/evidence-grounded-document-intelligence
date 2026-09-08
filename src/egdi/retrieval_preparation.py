"""Connect label-free visual routing to guarded retrieval-corpus preparation."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, Callable, Sequence

from .corpus import read_page_records_jsonl
from .io import write_json
from .ocr_corpus import build_ocr_corpus
from .text import PageRecord
from .visual_routing import (
    ROUTE_DOCUMENT_GLOBAL,
    ROUTE_LOCAL_VISUAL,
    ROUTE_SCANNED_DOCUMENT,
    ROUTE_TEXT,
    choose_visual_route,
)


OcrBuilder = Callable[..., dict[str, Any]]


def prepare_retrieval(
    question: str,
    native_records: Sequence[PageRecord],
    *,
    execute_ocr: bool = False,
    pdf_path: Path | None = None,
    ocr_output_dir: Path | None = None,
    pdftoppm: str | None = None,
    tesseract: str | None = None,
    ocr_builder: OcrBuilder = build_ocr_corpus,
) -> dict[str, Any]:
    """Plan or execute only the corpus action permitted by the selected route."""
    decision = choose_visual_route(question, native_records)
    route = decision["route"]
    base = {
        "schema_version": 1,
        "route_decision": decision,
        "execute_ocr_requested": execute_ocr,
        "uses_gold_or_answer_labels": False,
    }

    if route == ROUTE_TEXT:
        return {
            **base,
            "status": "ready",
            "action": "use_native_page_records",
            "corpus_kind": "native_text",
        }
    if route == ROUTE_LOCAL_VISUAL:
        return {
            **base,
            "status": "visual_evidence_required",
            "action": "render_retrieved_candidate_pages",
            "corpus_kind": "native_text",
        }
    if route == ROUTE_DOCUMENT_GLOBAL:
        return {
            **base,
            "status": "document_complete_processing_required",
            "action": "inspect_complete_document_or_abstain",
            "corpus_kind": None,
        }
    if route != ROUTE_SCANNED_DOCUMENT:  # pragma: no cover - closed route vocabulary
        raise RuntimeError(f"unsupported route: {route}")

    if not execute_ocr:
        return {
            **base,
            "status": "ocr_required",
            "action": "build_full_document_ocr_corpus",
            "corpus_kind": None,
        }

    missing = [
        name
        for name, value in (
            ("pdf_path", pdf_path),
            ("ocr_output_dir", ocr_output_dir),
            ("pdftoppm", pdftoppm),
            ("tesseract", tesseract),
        )
        if value is None
    ]
    if missing:
        raise ValueError(f"R2 OCR execution requires: {', '.join(missing)}")
    assert pdf_path is not None
    assert ocr_output_dir is not None
    assert pdftoppm is not None
    assert tesseract is not None
    doc_id = native_records[0].doc_id
    manifest = ocr_builder(
        pdf_path,
        doc_id,
        ocr_output_dir,
        pdftoppm=pdftoppm,
        tesseract=tesseract,
        dpi=200,
        language="eng",
        oem=1,
        psm=3,
    )
    return {
        **base,
        "status": "ready",
        "action": "use_ocr_page_records",
        "corpus_kind": "ocr_text",
        "ocr_output_dir": str(ocr_output_dir),
        "ocr_page_records": str(ocr_output_dir / "page_records.jsonl"),
        "ocr_manifest": manifest,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", required=True)
    parser.add_argument("--native-corpus", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--execute-ocr", action="store_true")
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--ocr-output-dir", type=Path)
    parser.add_argument("--pdftoppm", default=shutil.which("pdftoppm"))
    parser.add_argument("--tesseract", default=shutil.which("tesseract"))
    args = parser.parse_args()
    result = prepare_retrieval(
        args.question,
        read_page_records_jsonl(args.native_corpus),
        execute_ocr=args.execute_ocr,
        pdf_path=args.pdf,
        ocr_output_dir=args.ocr_output_dir,
        pdftoppm=args.pdftoppm,
        tesseract=args.tesseract,
    )
    write_json(args.output, result)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
