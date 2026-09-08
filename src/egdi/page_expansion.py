"""Evaluate deterministic adjacent-page expansion of a retrieved candidate pool."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .io import sha256_file, write_json


def expand_ranked_pages(
    ranked_pages: Sequence[int], *, page_count: int, radius: int = 1
) -> list[int]:
    """Expand each seed as seed, previous pages, then next pages, with stable dedup."""
    if isinstance(page_count, bool) or not isinstance(page_count, int) or page_count < 1:
        raise ValueError("page_count must be a positive integer")
    if isinstance(radius, bool) or not isinstance(radius, int) or radius < 0:
        raise ValueError("radius must be a non-negative integer")
    if not ranked_pages:
        raise ValueError("ranked_pages must not be empty")

    expanded: list[int] = []
    seen: set[int] = set()
    for seed in ranked_pages:
        if isinstance(seed, bool) or not isinstance(seed, int) or not 1 <= seed <= page_count:
            raise ValueError("ranked page is outside the document")
        candidates = [seed]
        candidates.extend(seed - offset for offset in range(1, radius + 1))
        candidates.extend(seed + offset for offset in range(1, radius + 1))
        for page in candidates:
            if 1 <= page <= page_count and page not in seen:
                expanded.append(page)
                seen.add(page)
    return expanded


def evaluate_adjacent_expansion(
    retrieval_result: dict[str, Any],
    page_count_by_doc: dict[str, int],
    *,
    seed_top_k: int = 10,
    radius: int = 1,
) -> dict[str, Any]:
    """Measure gold coverage only after deterministic candidate generation."""
    if isinstance(seed_top_k, bool) or not isinstance(seed_top_k, int) or seed_top_k < 1:
        raise ValueError("seed_top_k must be a positive integer")
    per_question = retrieval_result.get("per_question")
    if not isinstance(per_question, list) or not per_question:
        raise ValueError("retrieval result must contain per_question records")

    evaluated: list[dict[str, Any]] = []
    for record in per_question:
        doc_id = record.get("doc_id")
        if doc_id not in page_count_by_doc:
            raise ValueError(f"page count is missing for document: {doc_id}")
        seeds = record.get("retrieved_pages")
        gold_pages = record.get("gold_pages")
        if not isinstance(seeds, list) or len(seeds) < seed_top_k:
            raise ValueError("retrieval result has fewer seeds than seed_top_k")
        if not isinstance(gold_pages, list) or not gold_pages:
            raise ValueError("evaluation record must contain gold pages")
        seed_pages = seeds[:seed_top_k]
        candidates = expand_ranked_pages(
            seed_pages, page_count=page_count_by_doc[doc_id], radius=radius
        )
        gold = set(gold_pages)
        hits = sorted(gold.intersection(candidates))
        evaluated.append(
            {
                "question_id": record["question_id"],
                "doc_id": doc_id,
                "gold_pages": gold_pages,
                "seed_pages": seed_pages,
                "expanded_candidate_pages": candidates,
                "candidate_page_count": len(candidates),
                "gold_pages_found": hits,
                "any_evidence_recall": float(bool(hits)),
                "complete_evidence_recall": float(len(hits) == len(gold)),
                "recall": len(hits) / len(gold),
            }
        )

    count = len(evaluated)
    candidate_counts = [record["candidate_page_count"] for record in evaluated]
    return {
        "schema_version": 1,
        "split": retrieval_result.get("split"),
        "seed_top_k": seed_top_k,
        "radius": radius,
        "question_count": count,
        "aggregate": {
            "any_evidence_recall": sum(
                record["any_evidence_recall"] for record in evaluated
            )
            / count,
            "complete_evidence_recall": sum(
                record["complete_evidence_recall"] for record in evaluated
            )
            / count,
            "macro_recall": sum(record["recall"] for record in evaluated) / count,
            "candidate_page_count": {
                "minimum": min(candidate_counts),
                "maximum": max(candidate_counts),
                "mean": sum(candidate_counts) / count,
            },
        },
        "per_question": evaluated,
        "uses_gold_labels_only_after_candidate_generation": True,
    }


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retrieval-results", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    retrieval = _read_json(args.retrieval_results)
    inventory = _read_json(args.inventory)
    config = _read_json(args.config)
    expansion = config["expansion"]
    seed_top_k = config["input"]["seed_top_k"]
    page_counts = {
        document["doc_id"]: document["page_count"]
        for document in inventory["documents"]
    }
    result = evaluate_adjacent_expansion(
        retrieval,
        page_counts,
        seed_top_k=seed_top_k,
        radius=expansion["radius"],
    )
    result["inputs"] = {
        "retrieval_results_sha256": sha256_file(args.retrieval_results),
        "inventory_sha256": sha256_file(args.inventory),
        "config_sha256": sha256_file(args.config),
    }
    write_json(args.output, result)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "output_sha256": sha256_file(args.output),
                "question_count": result["question_count"],
                "aggregate": result["aggregate"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
