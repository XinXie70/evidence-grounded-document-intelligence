"""Run the pinned dense baseline on development_tune only."""

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
from .evaluation import DEFAULT_KS, evaluate_question
from .io import sha256_file, write_json
from .scoring import scoring_eligibility
from .text import PageRecord
from .tune_baseline import (
    _aggregate_results,
    _evidence_type,
    _gold_text_status,
    _read_json_object,
    load_tune_questions,
    load_verified_corpora,
)


def evaluate_dense_tune(
    questions: Sequence[dict[str, Any]],
    corpora: dict[str, list[PageRecord]],
    encoder: DenseEncoder,
    *,
    chunk_tokens: int,
    overlap_tokens: int,
    ks: Sequence[int] = DEFAULT_KS,
    progress_callback: Callable[[int, int, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Build one index per document and aggregate frozen evidence-page metrics."""
    if not questions:
        raise ValueError("at least one tune question is required")
    if not ks or any(isinstance(k, bool) or not isinstance(k, int) or k < 1 for k in ks):
        raise ValueError("ks must contain positive integers")

    eligible_by_doc: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    exclusions: list[dict[str, Any]] = []
    for ordinal, question in enumerate(questions):
        eligible, reason = scoring_eligibility(question)
        if not eligible:
            exclusions.append({"question_id": question.get("id"), "reason": reason})
            continue
        doc_id = question["pdf"]["doc_id_str"]
        if doc_id not in corpora:
            raise ValueError(f"no Page Record corpus for question document: {doc_id}")
        eligible_by_doc.setdefault(doc_id, []).append((ordinal, question))

    indexed_results: list[tuple[int, dict[str, Any]]] = []
    index_runs: list[dict[str, Any]] = []
    total_documents = len(eligible_by_doc)
    for document_number, (doc_id, indexed_questions) in enumerate(
        eligible_by_doc.items(), start=1
    ):
        records = corpora[doc_id]
        build_started = time.perf_counter()
        index = PageDenseIndex(
            records,
            encoder,
            chunk_tokens=chunk_tokens,
            overlap_tokens=overlap_tokens,
        )
        build_ms = (time.perf_counter() - build_started) * 1000
        index_run = {
            "doc_id": doc_id,
            "page_count": len(records),
            "chunk_count": len(index.chunks),
            "embedding_bytes": int(index.chunk_embeddings.nbytes),
            "build_latency_ms": build_ms,
        }
        index_runs.append(index_run)
        for ordinal, question in indexed_questions:
            query_started = time.perf_counter()
            result = evaluate_question(index, question, ks)
            result["query_latency_ms"] = (time.perf_counter() - query_started) * 1000
            result["doc_id"] = doc_id
            result["slices"] = {
                "page_span": "multi" if len(result["gold_pages"]) > 1 else "single",
                "gold_text_status": _gold_text_status(result["gold_pages"], records),
                "evidence_type": _evidence_type(question),
                "extract_class": str(question.get("extract_class", "unknown")),
            }
            indexed_results.append((ordinal, result))
        if progress_callback is not None:
            progress_callback(document_number, total_documents, index_run)

    per_question = [result for _, result in sorted(indexed_results)]
    slice_fields = ("page_span", "gold_text_status", "evidence_type", "extract_class")
    slices: dict[str, dict[str, Any]] = {}
    for field in slice_fields:
        categories = sorted({result["slices"][field] for result in per_question})
        slices[field] = {
            category: _aggregate_results(
                [result for result in per_question if result["slices"][field] == category],
                ks,
            )
            for category in categories
        }

    return {
        "split": "development_tune",
        "corpus_document_count": len(corpora),
        "evaluated_document_count": len(index_runs),
        "question_count": len(questions),
        "eligible_question_count": len(per_question),
        "excluded_question_count": len(exclusions),
        "exclusion_reasons": dict(Counter(item["reason"] for item in exclusions)),
        "exclusions": exclusions,
        "configuration": {
            "chunk_tokens": chunk_tokens,
            "overlap_tokens": overlap_tokens,
            "page_aggregation": "maximum_chunk_score",
        },
        "index_runs": index_runs,
        "total_embedding_bytes": sum(run["embedding_bytes"] for run in index_runs),
        "aggregate": _aggregate_results(per_question, ks),
        "slices": slices,
        "per_question": per_question,
    }


def _validated_choice(config: dict[str, Any], key: str, value: int) -> int:
    candidates = config.get(key)
    if not isinstance(candidates, list) or any(
        isinstance(candidate, bool) or not isinstance(candidate, int) for candidate in candidates
    ):
        raise ValueError(f"config {key} must be a list of integers")
    if value not in candidates:
        raise ValueError(f"selected value {value} is outside predeclared {key}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--split-manifest", required=True, type=Path)
    parser.add_argument("--corpus-manifest", required=True, type=Path)
    parser.add_argument("--corpus-dir", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--model-cache", required=True, type=Path)
    parser.add_argument("--chunk-tokens", required=True, type=int)
    parser.add_argument("--overlap-tokens", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    config = _read_json_object(args.config)
    if config.get("model_id") != BGE_SMALL_EN_V1_5_MODEL_ID:
        raise ValueError("config model_id does not match the pinned dense model")
    if config.get("model_revision") != BGE_SMALL_EN_V1_5_REVISION:
        raise ValueError("config model_revision does not match the pinned dense revision")
    chunk_tokens = _validated_choice(
        config, "chunk_token_candidates", args.chunk_tokens
    )
    overlap_tokens = _validated_choice(
        config, "overlap_token_candidates", args.overlap_tokens
    )
    if overlap_tokens >= chunk_tokens:
        raise ValueError("overlap_tokens must be smaller than chunk_tokens")
    ks = config.get("top_k_values")
    if not isinstance(ks, list):
        raise ValueError("config top_k_values must be a list")

    questions, document_ids = load_tune_questions(args.benchmark, args.split_manifest)
    corpora = load_verified_corpora(args.corpus_manifest, args.corpus_dir, document_ids)
    device = config.get("device")
    if device != "cpu":
        raise ValueError("config device must be cpu for the frozen dense baseline")
    encoder = SentenceTransformerBgeEncoder(cache_folder=str(args.model_cache), device=device)

    def report_progress(number: int, total: int, run: dict[str, Any]) -> None:
        print(
            f"[{number}/{total}] {run['doc_id']} pages={run['page_count']} "
            f"chunks={run['chunk_count']} build_ms={run['build_latency_ms']:.1f}",
            flush=True,
        )

    result = evaluate_dense_tune(
        questions,
        corpora,
        encoder,
        chunk_tokens=chunk_tokens,
        overlap_tokens=overlap_tokens,
        ks=ks,
        progress_callback=report_progress,
    )
    result["model_id"] = BGE_SMALL_EN_V1_5_MODEL_ID
    result["model_revision"] = BGE_SMALL_EN_V1_5_REVISION
    result["configuration_sha256"] = sha256_file(args.config)
    result["corpus_manifest_sha256"] = sha256_file(args.corpus_manifest)
    write_json(args.output, result)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "output_sha256": sha256_file(args.output),
                "evaluated_document_count": result["evaluated_document_count"],
                "eligible_question_count": result["eligible_question_count"],
                "excluded_question_count": result["excluded_question_count"],
                "total_embedding_bytes": result["total_embedding_bytes"],
                "aggregate": result["aggregate"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
