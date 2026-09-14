"""Build label-free BM25 + dense + RRF candidates for V1 routing inputs."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence

from .access import require_evaluation_split_access
from .bm25 import PageBm25Index
from .corpus import read_page_records_jsonl
from .dense import DenseEncoder, PageDenseIndex, SentenceTransformerBgeEncoder
from .io import sha256_file, write_json
from .rrf import reciprocal_rank_fusion
from .text import PageRecord
from .visual_routing import ROUTE_LOCAL_VISUAL, ROUTE_TEXT
from .visual_routing_v1 import ROUTING_POLICY_VERSION, choose_visual_route_v1


ALLOWED_SPLITS = {"development_tune", "development_calibration", "locked_test"}


def _safe_question(row: dict[str, Any]) -> dict[str, str]:
    result = {key: row.get(key) for key in ("pilot_id", "question_id", "doc_id", "question")}
    if any(not isinstance(value, str) or not value for value in result.values()):
        raise ValueError("selection row is missing an inference-time identity field")
    return result  # type: ignore[return-value]


def build_retrieval_candidates(
    rows: Sequence[dict[str, Any]],
    corpora: dict[str, list[PageRecord]],
    encoder: DenseEncoder,
    *,
    split: str,
    top_k: int = 10,
) -> dict[str, Any]:
    """Build candidates without accepting or emitting evaluation labels."""
    if split not in ALLOWED_SPLITS:
        raise ValueError("unknown evaluation split")
    require_evaluation_split_access(split)
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
        raise ValueError("top_k must be a positive integer")
    if not rows:
        raise ValueError("at least one selection row is required")

    safe_rows = [_safe_question(row) for row in rows]
    if len({row["question_id"] for row in safe_rows}) != len(safe_rows):
        raise ValueError("selection contains duplicate question IDs")
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in safe_rows:
        grouped[row["doc_id"]].append(row)

    output_rows: list[dict[str, Any]] = []
    route_counts: dict[str, int] = defaultdict(int)
    for doc_id in sorted(grouped):
        records = corpora.get(doc_id)
        if not records:
            raise ValueError(f"native corpus is missing: {doc_id}")
        bm25 = PageBm25Index(records, k1=1.2, b=0.75)
        dense = PageDenseIndex(records, encoder, chunk_tokens=256, overlap_tokens=0)
        depth = min(top_k, len(records))
        for row in grouped[doc_id]:
            route_record = choose_visual_route_v1(row["question"], records)
            route = route_record["route"]
            route_counts[route] += 1
            if route not in {ROUTE_TEXT, ROUTE_LOCAL_VISUAL}:
                continue
            bm25_results = bm25.search(row["question"], top_k=depth)
            dense_results = dense.search(row["question"], top_k=depth)
            bm25_pages = [item.page for item in bm25_results]
            dense_pages = [item.page for item in dense_results]
            fused = reciprocal_rank_fusion(
                [bm25_pages, dense_pages], rank_constant=60, top_k=depth
            )
            output_rows.append(
                {
                    **row,
                    "route": route,
                    "route_record": route_record,
                    "bm25_pages": bm25_pages,
                    "bm25_scores": [item.score for item in bm25_results],
                    "dense_pages": dense_pages,
                    "dense_scores": [item.score for item in dense_results],
                    "retrieved_pages": [page for page, _ in fused],
                    "rrf_scores": [score for _, score in fused],
                }
            )

    return {
        "schema_version": 1,
        "split": split,
        "status": "label_free_hybrid_candidates_frozen_before_reasoning",
        "contains_gold_or_answer_labels": False,
        "selection_question_count": len(safe_rows),
        "eligible_question_count": len(output_rows),
        "route_counts": dict(sorted(route_counts.items())),
        "configuration": {
            "bm25": {"k1": 1.2, "b": 0.75, "query_token_policy": "retain_repetitions"},
            "dense": {"model": "BAAI/bge-small-en-v1.5", "chunk_tokens": 256, "overlap_tokens": 0},
            "fusion": {"method": "reciprocal_rank_fusion", "rank_constant": 60, "weights": "equal"},
            "top_k": top_k,
            "routing_policy_version": ROUTING_POLICY_VERSION,
        },
        "per_question": output_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--page-records-manifest", required=True, type=Path)
    parser.add_argument("--page-records-dir", required=True, type=Path)
    parser.add_argument("--model-cache", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--top-k", type=int, default=10)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable output: {args.output}")

    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    split = selection.get("split")
    if split not in ALLOWED_SPLITS:
        raise ValueError("unknown selection split")
    require_evaluation_split_access(split)
    if selection.get("contains_gold_or_answer_labels") is not False:
        raise ValueError("selection must explicitly exclude gold and answer labels")
    rows = selection.get("questions")
    if not isinstance(rows, list) or not rows:
        raise ValueError("selection must contain questions")

    corpus_manifest = json.loads(args.page_records_manifest.read_text(encoding="utf-8"))
    expected = {
        item["doc_id"]: item["output_jsonl_sha256"]
        for item in corpus_manifest.get("documents", [])
    }
    doc_ids = sorted({_safe_question(row)["doc_id"] for row in rows})
    corpora: dict[str, list[PageRecord]] = {}
    for doc_id in doc_ids:
        path = args.page_records_dir / f"{doc_id}.jsonl"
        if doc_id not in expected:
            raise ValueError(f"page-record manifest is missing document: {doc_id}")
        if sha256_file(path) != expected[doc_id]:
            raise ValueError(f"page-record checksum mismatch: {doc_id}")
        corpora[doc_id] = read_page_records_jsonl(path)

    encoder = SentenceTransformerBgeEncoder(
        cache_folder=str(args.model_cache),
        device=args.device,
        local_files_only=True,
    )
    result = build_retrieval_candidates(
        rows, corpora, encoder, split=split, top_k=args.top_k
    )
    result["input_sha256"] = {
        "selection": sha256_file(args.selection),
        "page_records_manifest": sha256_file(args.page_records_manifest),
    }
    write_json(args.output, result)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "output_sha256": sha256_file(args.output),
                "selection_question_count": result["selection_question_count"],
                "eligible_question_count": result["eligible_question_count"],
                "route_counts": result["route_counts"],
                "contains_gold_or_answer_labels": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
