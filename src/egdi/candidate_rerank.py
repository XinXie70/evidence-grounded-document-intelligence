"""Question-aware dense reranking inside a frozen page candidate pool."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from .dense import DenseEncoder, PageDenseIndex, SentenceTransformerBgeEncoder
from .io import sha256_file, write_json
from .text import build_page_record


def build_reranked_reasoning_input(
    source: dict[str, Any],
    encoder: DenseEncoder,
    *,
    top_k: int,
    chunk_tokens: int = 256,
    overlap_tokens: int = 0,
) -> dict[str, Any]:
    """Rerank candidate pages while retaining full-page reasoning evidence."""
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
        raise ValueError("top_k must be a positive integer")
    if source.get("condition") != "real_retrieval":
        raise ValueError("source condition must be real_retrieval")
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
    if len(evidence) != len(pages) or len(evidence) < top_k:
        raise ValueError("source candidate pool is smaller than top_k or inconsistent")
    by_page: dict[int, dict[str, Any]] = {}
    records = []
    for expected_page, item in zip(pages, evidence, strict=True):
        if not isinstance(item, dict) or item.get("page") != expected_page:
            raise ValueError("source evidence order must match evidence_pages")
        page = item.get("page")
        text = item.get("text")
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise ValueError("candidate page must be a positive integer")
        if page in by_page:
            raise ValueError("candidate pages must be unique")
        if not isinstance(text, str):
            raise ValueError("candidate evidence text must be a string")
        by_page[page] = item
        records.append(build_page_record(source["doc_id"], page, text))

    ranked = PageDenseIndex(
        records,
        encoder,
        chunk_tokens=chunk_tokens,
        overlap_tokens=overlap_tokens,
    ).search(question, top_k=top_k)
    selected_pages = [result.page for result in ranked]
    result = copy.deepcopy(source)
    result["evidence_pages"] = selected_pages
    result["model_input"]["evidence"] = [copy.deepcopy(by_page[page]) for page in selected_pages]
    result["page_budget"] = top_k
    result["retriever"] = "hybrid_rrf_top10_dense_candidate_rerank_v0"
    result["candidate_rerank"] = {
        "candidate_page_count": len(pages),
        "chunk_tokens": chunk_tokens,
        "overlap_tokens": overlap_tokens,
        "page_aggregation": "maximum_chunk_score",
        "reasoning_evidence_scope": "full_selected_physical_pages",
        "ranking": [
            {
                "page": item.page,
                "score": item.score,
                "best_chunk_index": item.best_chunk_index,
            }
            for item in ranked
        ],
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model-cache", default="models/huggingface")
    parser.add_argument("--top-k", required=True, type=int)
    parser.add_argument("--chunk-tokens", default=256, type=int)
    parser.add_argument("--overlap-tokens", default=0, type=int)
    args = parser.parse_args()

    source = json.loads(args.input.read_text(encoding="utf-8"))
    encoder = SentenceTransformerBgeEncoder(
        cache_folder=args.model_cache,
        device="cpu",
        local_files_only=True,
    )
    result = build_reranked_reasoning_input(
        source,
        encoder,
        top_k=args.top_k,
        chunk_tokens=args.chunk_tokens,
        overlap_tokens=args.overlap_tokens,
    )
    result["candidate_rerank"]["source_input"] = str(args.input)
    result["candidate_rerank"]["source_input_sha256"] = sha256_file(args.input)
    write_json(args.output, result)
    print(json.dumps({
        "output": str(args.output),
        "selected_pages": result["evidence_pages"],
        "model_input_evidence_pages": [
            item["page"] for item in result["model_input"]["evidence"]
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
