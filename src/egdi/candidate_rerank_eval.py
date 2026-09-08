"""Evaluate dense reranking inside frozen RRF Top-10 candidates on tune only."""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Sequence

from .dense import (
    BGE_SMALL_EN_V1_5_MODEL_ID,
    BGE_SMALL_EN_V1_5_REVISION,
    DenseEncoder,
    PageDenseIndex,
    SentenceTransformerBgeEncoder,
)
from .io import sha256_file, write_json
from .scoring import aggregate_page_scores, score_evidence_pages
from .text import PageRecord
from .tune_baseline import load_verified_corpora


def _aggregate(results: Sequence[dict[str, Any]], ks: Sequence[int]) -> dict[str, Any]:
    return {
        str(k): aggregate_page_scores([
            score_evidence_pages(item["gold_pages"], item["retrieved_pages"], k)
            for item in results
        ])
        for k in ks
    }


def evaluate_candidate_rerank(
    rrf_run: dict[str, Any],
    corpora: dict[str, list[PageRecord]],
    encoder: DenseEncoder,
    *,
    candidate_depth: int = 10,
    chunk_tokens: int = 256,
    overlap_tokens: int = 0,
    ks: Sequence[int] = (1, 2, 3, 5, 10),
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    if rrf_run.get("split") != "development_tune":
        raise ValueError("candidate reranking input must be development_tune")
    questions = rrf_run.get("per_question")
    if not isinstance(questions, list) or not questions:
        raise ValueError("RRF run must contain per_question records")
    if (
        isinstance(candidate_depth, bool)
        or not isinstance(candidate_depth, int)
        or candidate_depth < max(ks)
    ):
        raise ValueError("candidate_depth must be at least the largest requested k")
    if list(ks) != sorted(set(ks)) or any(
        isinstance(k, bool) or not isinstance(k, int) or k < 1 for k in ks
    ):
        raise ValueError("ks must be unique increasing positive integers")

    by_doc: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for ordinal, question in enumerate(questions):
        doc_id = question.get("doc_id")
        if doc_id not in corpora:
            raise ValueError(f"no verified corpus for RRF question document: {doc_id}")
        candidates = question.get("retrieved_pages")
        if not isinstance(candidates, list) or len(candidates) < candidate_depth:
            raise ValueError(f"RRF candidate ranking is too short: {question.get('question_id')}")
        by_doc.setdefault(doc_id, []).append((ordinal, question))

    indexed: list[tuple[int, dict[str, Any]]] = []
    index_runs = []
    total_docs = len(by_doc)
    for doc_number, (doc_id, doc_questions) in enumerate(by_doc.items(), start=1):
        started = time.perf_counter()
        index = PageDenseIndex(
            corpora[doc_id],
            encoder,
            chunk_tokens=chunk_tokens,
            overlap_tokens=overlap_tokens,
        )
        index_runs.append({
            "doc_id": doc_id,
            "page_count": len(corpora[doc_id]),
            "chunk_count": len(index.chunks),
            "embedding_bytes": int(index.chunk_embeddings.nbytes),
            "build_latency_ms": (time.perf_counter() - started) * 1000,
        })
        for ordinal, question in doc_questions:
            candidates = question["retrieved_pages"][:candidate_depth]
            ranking = index.search_candidates(
                question["question"], candidates, top_k=max(ks)
            )
            pages = [item.page for item in ranking]
            indexed.append((ordinal, {
                "question_id": question["question_id"],
                "question": question["question"],
                "doc_id": doc_id,
                "gold_pages": question["gold_pages"],
                "candidate_pages": candidates,
                "retrieved_pages": pages,
                "dense_scores": [item.score for item in ranking],
                "best_chunk_indexes": [item.best_chunk_index for item in ranking],
                "scores": {
                    str(k): score_evidence_pages(
                        question["gold_pages"], pages, k
                    ).to_dict()
                    for k in ks
                },
                "slices": question["slices"],
            }))
        if progress_callback is not None:
            progress_callback(doc_number, total_docs, doc_id)

    per_question = [item for _, item in sorted(indexed)]
    slice_fields = ("page_span", "gold_text_status", "evidence_type", "extract_class")
    slices: dict[str, dict[str, Any]] = {}
    for field in slice_fields:
        categories = sorted({item["slices"][field] for item in per_question})
        slices[field] = {
            category: _aggregate(
                [item for item in per_question if item["slices"][field] == category],
                ks,
            )
            for category in categories
        }
    return {
        "schema_version": 1,
        "split": "development_tune",
        "question_count": len(per_question),
        "eligible_question_count": len(per_question),
        "excluded_question_count": rrf_run.get("excluded_question_count"),
        "exclusion_reasons": rrf_run.get("exclusion_reasons"),
        "aggregate": _aggregate(per_question, ks),
        "slices": slices,
        "per_question": per_question,
        "index_runs": index_runs,
        "total_embedding_bytes": sum(item["embedding_bytes"] for item in index_runs),
        "configuration": {
            "method": "dense_candidate_rerank",
            "candidate_source": "hybrid_rrf_bm25_dense_v0",
            "candidate_depth": candidate_depth,
            "chunk_tokens": chunk_tokens,
            "overlap_tokens": overlap_tokens,
            "page_aggregation": "maximum_chunk_score",
            "top_ks": list(ks),
        },
        "diagnostic_counts": dict(Counter(
            item["slices"]["page_span"] for item in per_question
        )),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rrf-run", required=True, type=Path)
    parser.add_argument("--corpus-manifest", required=True, type=Path)
    parser.add_argument("--corpus-dir", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--model-cache", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {args.output}")

    rrf_run = json.loads(args.rrf_run.read_text(encoding="utf-8"))
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if config.get("model_id") != BGE_SMALL_EN_V1_5_MODEL_ID:
        raise ValueError("config model_id does not match pinned BGE model")
    if config.get("model_revision") != BGE_SMALL_EN_V1_5_REVISION:
        raise ValueError("config model revision does not match pinned BGE revision")
    corpus_manifest = json.loads(args.corpus_manifest.read_text(encoding="utf-8"))
    manifest_documents = corpus_manifest.get("documents")
    if not isinstance(manifest_documents, list):
        raise ValueError("corpus manifest is missing documents")
    manifest_doc_ids = [item.get("doc_id") for item in manifest_documents]
    if not all(isinstance(doc_id, str) for doc_id in manifest_doc_ids):
        raise ValueError("corpus manifest contains an invalid doc_id")
    corpora = load_verified_corpora(
        args.corpus_manifest, args.corpus_dir, manifest_doc_ids
    )
    encoder = SentenceTransformerBgeEncoder(
        cache_folder=str(args.model_cache), device="cpu", local_files_only=True
    )

    def progress(number: int, total: int, doc_id: str) -> None:
        print(f"[{number}/{total}] {doc_id}", flush=True)

    result = evaluate_candidate_rerank(
        rrf_run,
        corpora,
        encoder,
        candidate_depth=config["candidate_depth"],
        chunk_tokens=config["chunk_tokens"],
        overlap_tokens=config["overlap_tokens"],
        ks=config["top_ks"],
        progress_callback=progress,
    )
    result["configuration"] = config
    result["input_sha256"] = {
        "rrf_run": sha256_file(args.rrf_run),
        "corpus_manifest": sha256_file(args.corpus_manifest),
    }
    result["configuration_sha256"] = sha256_file(args.config)
    write_json(args.output, result)
    print(json.dumps({
        "output": str(args.output),
        "output_sha256": sha256_file(args.output),
        "eligible_question_count": result["eligible_question_count"],
        "aggregate": result["aggregate"],
    }, indent=2))


if __name__ == "__main__":
    main()
