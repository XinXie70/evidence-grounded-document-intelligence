"""Build deterministic page-bounded OCR corpora from fully scanned PDFs."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

from .corpus import read_page_records_jsonl, write_page_records_jsonl
from .io import sha256_file, write_json
from .text import PageRecord, build_page_record


_RENDERED_PAGE = re.compile(r"^render-(\d+)\.png$")


def build_render_command(
    pdftoppm: str, pdf_path: Path, output_prefix: Path, *, dpi: int = 200
) -> list[str]:
    """Return the pinned full-document Poppler rendering command."""
    if isinstance(dpi, bool) or not isinstance(dpi, int) or dpi < 1:
        raise ValueError("dpi must be a positive integer")
    return [pdftoppm, "-png", "-r", str(dpi), str(pdf_path), str(output_prefix)]


def build_tesseract_command(
    tesseract: str,
    image_path: Path,
    output_base: Path,
    *,
    language: str = "eng",
    oem: int = 1,
    psm: int = 3,
) -> list[str]:
    """Return one pinned, page-local Tesseract command."""
    if not isinstance(language, str) or not language.strip():
        raise ValueError("language must be a non-empty string")
    if isinstance(oem, bool) or not isinstance(oem, int) or oem not in range(4):
        raise ValueError("oem must be an integer from 0 through 3")
    if isinstance(psm, bool) or not isinstance(psm, int) or psm not in range(14):
        raise ValueError("psm must be an integer from 0 through 13")
    return [
        tesseract,
        str(image_path),
        str(output_base),
        "-l",
        language,
        "--oem",
        str(oem),
        "--psm",
        str(psm),
    ]


def discover_rendered_pages(pages_dir: Path) -> list[tuple[int, Path]]:
    """Find Poppler PNGs and reject gaps or duplicate physical page numbers."""
    by_page: dict[int, Path] = {}
    for path in pages_dir.iterdir():
        match = _RENDERED_PAGE.fullmatch(path.name)
        if match is None:
            continue
        page = int(match.group(1))
        if page in by_page:
            raise ValueError(f"duplicate rendered page number: {page}")
        by_page[page] = path
    pages = sorted(by_page.items())
    if [page for page, _ in pages] != list(range(1, len(pages) + 1)):
        raise ValueError("rendered pages must be sequential from physical page 1")
    return pages


def _tool_version(executable: str, flag: str) -> str:
    completed = subprocess.run(
        [executable, flag], check=True, capture_output=True, text=True
    )
    lines = [
        line.strip()
        for line in (completed.stdout + "\n" + completed.stderr).splitlines()
        if line.strip()
    ]
    if not lines:
        raise RuntimeError(f"could not determine tool version: {executable}")
    return lines[0]


def _pdf_page_count(pdf_path: Path) -> int:
    try:
        from pypdf import PdfReader
    except ImportError as error:  # pragma: no cover - dependency is pinned by the project
        raise RuntimeError("pypdf is required to count PDF pages") from error
    return len(PdfReader(str(pdf_path), strict=False).pages)


def build_ocr_corpus(
    pdf_path: Path,
    doc_id: str,
    output_dir: Path,
    *,
    pdftoppm: str,
    tesseract: str,
    dpi: int = 200,
    language: str = "eng",
    oem: int = 1,
    psm: int = 3,
) -> dict[str, Any]:
    """Render, OCR, verify, and record one scanned PDF without answer labels."""
    if not pdf_path.is_file():
        raise FileNotFoundError(f"source PDF does not exist: {pdf_path}")
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing OCR output: {output_dir}")
    staging_dir = output_dir.with_name(output_dir.name + ".partial")
    if staging_dir.exists():
        raise FileExistsError(f"unfinished OCR staging output already exists: {staging_dir}")

    page_count = _pdf_page_count(pdf_path)
    if page_count < 1:
        raise ValueError("source PDF must contain at least one page")
    pdftoppm_version = _tool_version(pdftoppm, "-v")
    tesseract_version = _tool_version(tesseract, "--version")

    pages_dir = staging_dir / "pages"
    text_dir = staging_dir / "text"
    pages_dir.mkdir(parents=True)
    text_dir.mkdir()

    render_command = build_render_command(
        pdftoppm, pdf_path, pages_dir / "render", dpi=dpi
    )
    subprocess.run(render_command, check=True, capture_output=True, text=True)
    rendered = discover_rendered_pages(pages_dir)
    if len(rendered) != page_count:
        raise RuntimeError(
            f"rendered page count mismatch: expected {page_count}, found {len(rendered)}"
        )

    records: list[PageRecord] = []
    page_manifest: list[dict[str, Any]] = []
    for page, rendered_path in rendered:
        image_path = pages_dir / f"page-{page:04d}.png"
        rendered_path.replace(image_path)
        output_base = text_dir / f"page-{page:04d}"
        ocr_command = build_tesseract_command(
            tesseract,
            image_path,
            output_base,
            language=language,
            oem=oem,
            psm=psm,
        )
        subprocess.run(ocr_command, check=True, capture_output=True, text=True)
        text_path = output_base.with_suffix(".txt")
        if not text_path.is_file():
            raise RuntimeError(f"Tesseract did not create text for physical page {page}")
        raw_text = text_path.read_text(encoding="utf-8")
        record = build_page_record(doc_id, page, raw_text)
        records.append(record)
        page_manifest.append(
            {
                "page": page,
                "image": str(image_path.relative_to(staging_dir)),
                "image_sha256": sha256_file(image_path),
                "text": str(text_path.relative_to(staging_dir)),
                "text_sha256": sha256_file(text_path),
                "non_whitespace_chars": record.non_whitespace_chars,
                "extraction_status": record.extraction_status,
            }
        )

    corpus_path = staging_dir / "page_records.jsonl"
    write_page_records_jsonl(corpus_path, records)
    if read_page_records_jsonl(corpus_path) != records:
        raise RuntimeError("OCR Page Record round-trip verification failed")

    status_counts = Counter(record.extraction_status for record in records)
    manifest = {
        "schema_version": 1,
        "doc_id": doc_id,
        "source_pdf": str(pdf_path),
        "source_pdf_sha256": sha256_file(pdf_path),
        "page_count": page_count,
        "rendering": {
            "tool": "pdftoppm",
            "executable": pdftoppm,
            "version": pdftoppm_version,
            "dpi": dpi,
            "format": "png",
            "command": render_command,
        },
        "ocr": {
            "tool": "tesseract",
            "executable": tesseract,
            "version": tesseract_version,
            "language": language,
            "oem": oem,
            "psm": psm,
        },
        "page_records": {
            "path": str(corpus_path.relative_to(staging_dir)),
            "sha256": sha256_file(corpus_path),
            "record_count": len(records),
            "status_counts": {
                status: status_counts.get(status, 0)
                for status in ("ok", "low_text", "text_layer_missing")
            },
        },
        "pages": page_manifest,
    }
    write_json(staging_dir / "manifest.json", manifest)
    staging_dir.replace(output_dir)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--doc-id", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--pdftoppm", default=shutil.which("pdftoppm"))
    parser.add_argument("--tesseract", default=shutil.which("tesseract"))
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--language", default="eng")
    parser.add_argument("--oem", type=int, default=1)
    parser.add_argument("--psm", type=int, default=3)
    args = parser.parse_args()
    if not args.pdftoppm:
        raise RuntimeError("pdftoppm was not found; pass --pdftoppm explicitly")
    if not args.tesseract:
        raise RuntimeError("tesseract was not found; pass --tesseract explicitly")
    manifest = build_ocr_corpus(
        args.pdf,
        args.doc_id,
        args.output_dir,
        pdftoppm=args.pdftoppm,
        tesseract=args.tesseract,
        dpi=args.dpi,
        language=args.language,
        oem=args.oem,
        psm=args.psm,
    )
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir),
                "manifest_sha256": sha256_file(args.output_dir / "manifest.json"),
                "page_count": manifest["page_count"],
                "status_counts": manifest["page_records"]["status_counts"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
