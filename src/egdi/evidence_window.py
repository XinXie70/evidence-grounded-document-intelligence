"""Page-bounded chunk windows for fine-grained evidence diagnostics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .dense import DenseChunk, DenseEncoder, PageDenseIndex, SentenceTransformerBgeEncoder
from .io import sha256_file, write_json
from .text import build_page_record


def select_chunk_window(
    chunks: Sequence[DenseChunk],
    *,
    page: int,
    best_chunk_index: int,
    before_chunks: int,
    after_chunks: int,
) -> list[DenseChunk]:
    """Select a deterministic neighboring window without crossing a page boundary."""
    for name, value in (
        ("page", page),
        ("best_chunk_index", best_chunk_index),
        ("before_chunks", before_chunks),
        ("after_chunks", after_chunks),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")
    if page < 1:
        raise ValueError("page must be positive")

    page_chunks = sorted(
        (chunk for chunk in chunks if chunk.page == page),
        key=lambda chunk: chunk.chunk_index,
    )
    indexes = [chunk.chunk_index for chunk in page_chunks]
    if best_chunk_index not in indexes:
        raise ValueError("best_chunk_index is absent from the requested page")
    lower = max(0, best_chunk_index - before_chunks)
    upper = best_chunk_index + after_chunks
    return [chunk for chunk in page_chunks if lower <= chunk.chunk_index <= upper]


def build_page_localization_diagnostic(
    source: dict[str, Any],
    encoder: DenseEncoder,
    *,
    chunk_tokens: int = 256,
    overlap_tokens: int = 0,
    before_chunks: int = 2,
    after_chunks: int = 1,
) -> dict[str, Any]:
    """Localize evidence within supplied pages while retaining physical-page identity."""
    model_input = source.get("model_input")
    if not isinstance(model_input, dict):
        raise ValueError("source must contain model_input")
    question = model_input.get("question")
    evidence = model_input.get("evidence")
    pages = source.get("evidence_pages")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("source question must be non-empty")
    if not isinstance(evidence, list) or not isinstance(pages, list):
        raise ValueError("source evidence and evidence_pages must be lists")
    if len(evidence) != len(pages) or not evidence:
        raise ValueError("source evidence and evidence_pages must be non-empty and aligned")

    records = []
    full_chars = 0
    for expected_page, item in zip(pages, evidence, strict=True):
        if not isinstance(item, dict) or item.get("page") != expected_page:
            raise ValueError("source evidence order must match evidence_pages")
        text = item.get("text")
        if not isinstance(text, str):
            raise ValueError("evidence text must be a string")
        records.append(build_page_record(source["doc_id"], expected_page, text))
        full_chars += len(text)

    index = PageDenseIndex(
        records,
        encoder,
        chunk_tokens=chunk_tokens,
        overlap_tokens=overlap_tokens,
    )
    localized = []
    best_only_chars = 0
    expanded_chars = 0
    for page in pages:
        best = index.search_candidates(question, [page], top_k=1)[0]
        best_chunk = next(
            chunk
            for chunk in index.chunks
            if chunk.page == page and chunk.chunk_index == best.best_chunk_index
        )
        window = select_chunk_window(
            index.chunks,
            page=page,
            best_chunk_index=best.best_chunk_index,
            before_chunks=before_chunks,
            after_chunks=after_chunks,
        )
        expanded_text = " ".join(chunk.text for chunk in window)
        best_only_chars += len(best_chunk.text)
        expanded_chars += len(expanded_text)
        localized.append(
            {
                "page": page,
                "best_chunk_index": best.best_chunk_index,
                "best_chunk_score": best.score,
                "page_chunk_count": sum(chunk.page == page for chunk in index.chunks),
                "best_only_text": best_chunk.text,
                "expanded_chunk_indexes": [chunk.chunk_index for chunk in window],
                "expanded_text": expanded_text,
            }
        )

    return {
        "schema_version": 1,
        "experiment_type": "oracle_page_within_page_localization_diagnostic",
        "question_id": source.get("question_id"),
        "doc_id": source.get("doc_id"),
        "question": question,
        "pages": pages,
        "configuration": {
            "chunk_tokens": chunk_tokens,
            "overlap_tokens": overlap_tokens,
            "before_chunks": before_chunks,
            "after_chunks": after_chunks,
            "uses_gold_pages_to_isolate_within_page_localization": True,
            "paid_api_used": False,
        },
        "character_counts": {
            "full_pages": full_chars,
            "best_chunks_only": best_only_chars,
            "expanded_windows": expanded_chars,
        },
        "localized_evidence": localized,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model-cache", default="models/huggingface")
    parser.add_argument("--chunk-tokens", default=256, type=int)
    parser.add_argument("--overlap-tokens", default=0, type=int)
    parser.add_argument("--before-chunks", default=2, type=int)
    parser.add_argument("--after-chunks", default=1, type=int)
    args = parser.parse_args()

    source = json.loads(args.input.read_text(encoding="utf-8"))
    encoder = SentenceTransformerBgeEncoder(
        cache_folder=args.model_cache,
        device="cpu",
        local_files_only=True,
    )
    result = build_page_localization_diagnostic(
        source,
        encoder,
        chunk_tokens=args.chunk_tokens,
        overlap_tokens=args.overlap_tokens,
        before_chunks=args.before_chunks,
        after_chunks=args.after_chunks,
    )
    result["source_input"] = str(args.input)
    result["source_input_sha256"] = sha256_file(args.input)
    write_json(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
