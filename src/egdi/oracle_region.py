"""Deterministically render DocScope gold evidence bounding-box crops."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
from typing import Any

from .access import load_records
from .io import sha256_file, write_json


DOCSCOPE_RENDER_DPI = 144
DOCSCOPE_COORDINATE_SPACE = "cropbox_pixels_at_144_dpi_top_left_origin"


def bbox_to_pixel_crop(bbox: list[Any]) -> tuple[int, int, int, int]:
    """Round a DocScope [x1,y1,x2,y2] box outward to pixel edges."""
    if len(bbox) != 4 or any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        for value in bbox
    ):
        raise ValueError("bbox must contain four finite numbers")
    x1, y1, x2, y2 = bbox
    if x1 < 0 or y1 < 0 or x2 <= x1 or y2 <= y1:
        raise ValueError("bbox must have non-negative origin and positive area")
    return math.floor(x1), math.floor(y1), math.ceil(x2), math.ceil(y2)


def build_crop_specs(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Select only question/evidence location fields; never expose answers or facts."""
    question_id = record.get("id")
    question = record.get("question")
    pdf = record.get("pdf")
    evidences = record.get("evidences")
    if not isinstance(question_id, str) or not question_id:
        raise ValueError("record.id must be a non-empty string")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("record.question must be a non-empty string")
    if not isinstance(pdf, dict) or not isinstance(pdf.get("doc_id_str"), str):
        raise ValueError("record.pdf.doc_id_str must be a string")
    if not isinstance(evidences, list) or not evidences:
        raise ValueError("record.evidences must be a non-empty list")

    specs: list[dict[str, Any]] = []
    for evidence in evidences:
        if not isinstance(evidence, dict):
            raise ValueError("each evidence must be an object")
        local_id = evidence.get("local_id")
        page = evidence.get("page")
        element_type = evidence.get("element_type")
        bbox = evidence.get("bbox")
        if not isinstance(local_id, str) or not local_id:
            raise ValueError("evidence.local_id must be a non-empty string")
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise ValueError("evidence.page must be a positive integer")
        if not isinstance(element_type, str) or not element_type:
            raise ValueError("evidence.element_type must be a non-empty string")
        if not isinstance(bbox, list):
            raise ValueError("evidence.bbox must be a list")
        pixel_crop = bbox_to_pixel_crop(bbox)
        specs.append(
            {
                "question_id": question_id,
                "doc_id": pdf["doc_id_str"],
                "question": question,
                "evidence_local_id": local_id,
                "page": page,
                "element_type": element_type,
                "bbox": bbox,
                "pixel_crop": list(pixel_crop),
            }
        )
    return specs


def build_pdftoppm_command(
    pdftoppm: str, pdf_path: Path, output_prefix: Path, spec: dict[str, Any]
) -> list[str]:
    left, top, right, bottom = spec["pixel_crop"]
    return [
        pdftoppm,
        "-f",
        str(spec["page"]),
        "-l",
        str(spec["page"]),
        "-r",
        str(DOCSCOPE_RENDER_DPI),
        "-png",
        "-cropbox",
        "-x",
        str(left),
        "-y",
        str(top),
        "-W",
        str(right - left),
        "-H",
        str(bottom - top),
        "-singlefile",
        str(pdf_path),
        str(output_prefix),
    ]


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        header = stream.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"rendered crop is not a valid PNG: {path}")
    return struct.unpack(">II", header[16:24])


def render_question_crops(
    record: dict[str, Any],
    *,
    benchmark_path: Path,
    pdf_root: Path,
    output_dir: Path,
    pdftoppm: str,
) -> dict[str, Any]:
    specs = build_crop_specs(record)
    doc_id = specs[0]["doc_id"]
    if any(spec["doc_id"] != doc_id for spec in specs):
        raise ValueError("all evidence crops must belong to one document")
    pdf_path = pdf_root / f"{doc_id}.pdf"
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)
    manifest_path = output_dir / "manifest.json"
    if manifest_path.exists():
        raise FileExistsError(f"refusing to overwrite immutable manifest: {manifest_path}")
    output_dir.mkdir(parents=True, exist_ok=True)

    rendered: list[dict[str, Any]] = []
    for spec in specs:
        filename = f"{spec['evidence_local_id']}_page_{spec['page']:04d}.png"
        output_png = output_dir / filename
        if output_png.exists():
            raise FileExistsError(f"refusing to overwrite immutable crop: {output_png}")
        command = build_pdftoppm_command(
            pdftoppm, pdf_path, output_png.with_suffix(""), spec
        )
        subprocess.run(command, check=True, capture_output=True, text=True)
        width, height = png_dimensions(output_png)
        rendered.append(
            {
                **spec,
                "output_png": filename,
                "output_png_sha256": sha256_file(output_png),
                "output_width_pixels": width,
                "output_height_pixels": height,
            }
        )

    manifest = {
        "schema_version": 1,
        "status": "manual_review_required",
        "question_id": specs[0]["question_id"],
        "doc_id": doc_id,
        "question": specs[0]["question"],
        "coordinate_space": DOCSCOPE_COORDINATE_SPACE,
        "render_dpi": DOCSCOPE_RENDER_DPI,
        "use_pdf_cropbox": True,
        "rounding_rule": "floor x1/y1 and ceil x2/y2",
        "benchmark_path": str(benchmark_path),
        "benchmark_sha256": sha256_file(benchmark_path),
        "source_pdf": str(pdf_path),
        "source_pdf_sha256": sha256_file(pdf_path),
        "crops": rendered,
    }
    write_json(manifest_path, manifest)
    return manifest


def _load_question(benchmark_path: Path, question_id: str) -> dict[str, Any]:
    # Oracle-region development is restricted to the development split.  In
    # particular, do not let this convenience CLI bypass the locked-test guard.
    records = load_records(benchmark_path, split="dev")
    matches = [record for record in records if record.get("id") == question_id]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one benchmark record for {question_id}")
    return matches[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--pdf-root", required=True, type=Path)
    parser.add_argument("--question-id", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--pdftoppm", default=shutil.which("pdftoppm"))
    args = parser.parse_args()
    if not args.pdftoppm:
        raise RuntimeError("pdftoppm was not found")
    record = _load_question(args.benchmark, args.question_id)
    manifest = render_question_crops(
        record,
        benchmark_path=args.benchmark,
        pdf_root=args.pdf_root,
        output_dir=args.output_dir,
        pdftoppm=args.pdftoppm,
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
