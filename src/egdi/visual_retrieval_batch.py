"""Render, cache, and blindly rerank RRF pages with the pinned visual encoder."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from .access import require_evaluation_split_access
from .io import sha256_file, write_json
from .visual_encoder import (
    COLSMOL_256M_BASE_MODEL_ID,
    COLSMOL_256M_BASE_REVISION,
    COLSMOL_256M_MODEL_ID,
    COLSMOL_256M_REVISION,
    SentenceTransformerColSmolEncoder,
)
from .visual_multivector import build_candidate_page_render_command, rerank_visual_pages
from .visual_runtime_manifest import _contains_forbidden_key


PageIdentity = tuple[str, int]


def unique_candidate_pages(manifest: dict[str, Any]) -> list[PageIdentity]:
    """Return stable document/page identities from a label-free runtime manifest."""
    if manifest.get("contains_gold_or_answer_labels") is not False:
        raise ValueError("manifest must explicitly exclude gold and answer labels")
    if _contains_forbidden_key(manifest):
        raise ValueError("manifest contains a forbidden evaluation field")
    questions = manifest.get("questions")
    if not isinstance(questions, list) or not questions:
        raise ValueError("manifest must contain questions")
    identities: set[PageIdentity] = set()
    for item in questions:
        doc_id = item.get("doc_id")
        pages = item.get("candidate_pages")
        if not isinstance(doc_id, str) or not doc_id:
            raise ValueError("question doc_id must be a non-empty string")
        if not isinstance(pages, list) or not pages:
            raise ValueError("candidate_pages must be a non-empty list")
        if any(isinstance(page, bool) or not isinstance(page, int) or page < 1 for page in pages):
            raise ValueError("candidate_pages must contain positive integers")
        if len(pages) != len(set(pages)):
            raise ValueError("candidate_pages must be unique within each question")
        identities.update((doc_id, page) for page in pages)
    return sorted(identities)


def embedding_cache_path(cache_dir: Path, doc_id: str, page: int) -> Path:
    return cache_dir / "embeddings" / doc_id / f"page-{page:04d}.npy"


def image_cache_path(cache_dir: Path, doc_id: str, page: int) -> Path:
    return cache_dir / "pages" / doc_id / f"page-{page:04d}.png"


def load_cached_embedding(path: Path) -> NDArray[np.float32]:
    """Load one complete finite float32 page embedding, rejecting corrupt caches."""
    values = np.load(path, allow_pickle=False)
    if values.ndim != 2 or values.shape[0] == 0 or values.shape[1] == 0:
        raise ValueError(f"cached embedding must be a non-empty 2D matrix: {path}")
    if not np.issubdtype(values.dtype, np.floating) or not np.isfinite(values).all():
        raise ValueError(f"cached embedding must contain finite floating-point values: {path}")
    return np.asarray(values, dtype=np.float32)


def save_embedding_atomic(path: Path, values: NDArray[np.floating]) -> None:
    matrix = np.asarray(values, dtype=np.float32)
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise ValueError("page embedding must be a non-empty 2D matrix")
    if not np.isfinite(matrix).all():
        raise ValueError("page embedding must contain only finite values")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    if temporary.exists():
        temporary.unlink()
    with temporary.open("wb") as handle:
        np.save(handle, matrix, allow_pickle=False)
    temporary.replace(path)


def _chunks(values: Sequence[PageIdentity], size: int) -> Iterable[list[PageIdentity]]:
    for start in range(0, len(values), size):
        yield list(values[start : start + size])


def render_candidate_page(
    *,
    pdftoppm: str,
    pdf_path: Path,
    output_path: Path,
    physical_page: int,
    dpi: int,
) -> None:
    """Render one page atomically; an existing valid PNG is an immutable cache hit."""
    if output_path.exists():
        try:
            with Image.open(output_path) as image:
                image.verify()
        except Exception as error:
            raise ValueError(f"existing cached page image is invalid: {output_path}") from error
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_prefix = output_path.parent / f"{output_path.stem}.partial"
    temporary_image = Path(str(temporary_prefix) + ".png")
    if temporary_image.exists():
        temporary_image.unlink()
    command = build_candidate_page_render_command(
        pdftoppm,
        pdf_path,
        temporary_prefix,
        physical_page,
        dpi=dpi,
    )
    subprocess.run(command, check=True, capture_output=True, text=True)
    if not temporary_image.is_file():
        raise RuntimeError(f"renderer did not create expected page image: {temporary_image}")
    with Image.open(temporary_image) as image:
        image.verify()
    temporary_image.replace(output_path)


def build_blind_rankings(
    manifest: dict[str, Any],
    *,
    encode_query: Callable[[str], NDArray[np.floating]],
    load_page_embedding: Callable[[str, int], NDArray[np.floating]],
) -> list[dict[str, Any]]:
    """Create visual rankings without accepting any evaluation labels."""
    unique_candidate_pages(manifest)
    rankings: list[dict[str, Any]] = []
    for item in manifest["questions"]:
        query = encode_query(item["question"])
        pages = item["candidate_pages"]
        embeddings = {page: load_page_embedding(item["doc_id"], page) for page in pages}
        reranked = rerank_visual_pages(pages, query, embeddings)
        rankings.append(
            {
                "question_id": item["question_id"],
                "doc_id": item["doc_id"],
                "original_rrf_pages": pages,
                "visual_reranked_pages": [result.page for result in reranked],
                "visual_scores": [result.score for result in reranked],
                "original_rrf_ranks": [result.original_rank for result in reranked],
            }
        )
    return rankings


def _tool_version(executable: str) -> str:
    completed = subprocess.run(
        [executable, "-v"], check=True, capture_output=True, text=True
    )
    lines = [
        line.strip()
        for line in (completed.stdout + "\n" + completed.stderr).splitlines()
        if line.strip()
    ]
    if not lines:
        raise RuntimeError("could not determine pdftoppm version")
    return lines[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--pdf-root", required=True, type=Path)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--pdftoppm", default=shutil.which("pdftoppm"))
    parser.add_argument("--model-cache", default="models/huggingface")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--batch-size", type=int, default=2)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable output: {args.output}")
    if isinstance(args.batch_size, bool) or args.batch_size < 1:
        raise ValueError("batch-size must be a positive integer")

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    split = manifest.get("split")
    if split not in {"development_tune", "development_calibration", "locked_test"}:
        raise ValueError("unknown evaluation split")
    require_evaluation_split_access(split)
    identities = unique_candidate_pages(manifest)
    for render_index, (doc_id, page) in enumerate(identities, start=1):
        pdf_path = args.pdf_root / f"{doc_id}.pdf"
        if not pdf_path.is_file():
            raise FileNotFoundError(pdf_path)
        cached_image = image_cache_path(args.cache_dir, doc_id, page)
        if not args.pdftoppm and not cached_image.exists():
            raise RuntimeError(
                "pdftoppm was not found and a candidate page is not cached; "
                "pass --pdftoppm explicitly"
            )
        render_candidate_page(
            pdftoppm=args.pdftoppm or "pdftoppm",
            pdf_path=pdf_path,
            output_path=cached_image,
            physical_page=page,
            dpi=args.dpi,
        )
        if render_index % 10 == 0 or render_index == len(identities):
            print(f"[{render_index}/{len(identities)}] visual pages rendered/cached", flush=True)

    pending = [
        identity
        for identity in identities
        if not embedding_cache_path(args.cache_dir, *identity).exists()
    ]
    encoder = SentenceTransformerColSmolEncoder(
        args.model_cache,
        device=args.device,
        local_files_only=True,
    )
    started = time.perf_counter()
    completed_count = len(identities) - len(pending)
    for batch in _chunks(pending, args.batch_size):
        images = []
        for doc_id, page in batch:
            with Image.open(image_cache_path(args.cache_dir, doc_id, page)) as source:
                images.append(source.convert("RGB"))
        embeddings = encoder.encode_pages(images, batch_size=args.batch_size)
        for identity, embedding in zip(batch, embeddings, strict=True):
            save_embedding_atomic(embedding_cache_path(args.cache_dir, *identity), embedding)
        completed_count += len(batch)
        print(f"[{completed_count}/{len(identities)}] visual page embeddings cached", flush=True)

    rankings = build_blind_rankings(
        manifest,
        encode_query=encoder.encode_query,
        load_page_embedding=lambda doc_id, page: load_cached_embedding(
            embedding_cache_path(args.cache_dir, doc_id, page)
        ),
    )
    page_artifacts = [
        {
            "doc_id": doc_id,
            "page": page,
            "image_sha256": sha256_file(image_cache_path(args.cache_dir, doc_id, page)),
            "embedding_sha256": sha256_file(embedding_cache_path(args.cache_dir, doc_id, page)),
        }
        for doc_id, page in identities
    ]
    output = {
        "schema_version": 1,
        "split": split,
        "status": "blind_visual_rankings_frozen_before_scoring",
        "contains_gold_or_answer_labels": False,
        "question_count": len(rankings),
        "unique_candidate_page_count": len(identities),
        "configuration": {
            "model_id": COLSMOL_256M_MODEL_ID,
            "model_revision": COLSMOL_256M_REVISION,
            "base_model_id": COLSMOL_256M_BASE_MODEL_ID,
            "base_model_revision": COLSMOL_256M_BASE_REVISION,
            "device": args.device,
            "dpi": args.dpi,
            "batch_size": args.batch_size,
            "scoring": "normalized_colbert_late_interaction_sum_max",
            "tie_break": "preserve_original_rrf_order",
            "pdftoppm_version": (
                _tool_version(args.pdftoppm) if args.pdftoppm else "cached_pages_reused"
            ),
        },
        "input_sha256": {"runtime_manifest": sha256_file(args.manifest)},
        "elapsed_seconds_excluding_existing_cache": time.perf_counter() - started,
        "page_artifacts": page_artifacts,
        "rankings": rankings,
    }
    if _contains_forbidden_key(output):
        raise ValueError("blind output contains a forbidden evaluation field")
    write_json(args.output, output)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "output_sha256": sha256_file(args.output),
                "question_count": output["question_count"],
                "unique_candidate_page_count": output["unique_candidate_page_count"],
                "contains_gold_or_answer_labels": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
