"""Score bounded contiguous page windows for scanned-document retrieval."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .bm25 import PageBm25Index
from .io import sha256_file, write_json
from .r2_evaluate import load_registered_r2_corpora, select_inventory_questions
from .tune_baseline import load_tune_questions


def select_non_overlapping_windows(
    page_scores: dict[int, float],
    *,
    page_count: int,
    window_width: int = 3,
    window_count: int = 3,
) -> list[dict[str, Any]]:
    """Rank window sums, then greedily retain non-overlapping windows."""
    for name, value in (
        ("page_count", page_count),
        ("window_width", window_width),
        ("window_count", window_count),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    if window_width > page_count:
        raise ValueError("window_width cannot exceed page_count")
    if set(page_scores) != set(range(1, page_count + 1)):
        raise ValueError("page_scores must cover every physical page exactly once")
    if any(isinstance(score, bool) or not isinstance(score, (int, float)) for score in page_scores.values()):
        raise ValueError("page scores must be numeric")

    ranked: list[dict[str, Any]] = []
    for start in range(1, page_count - window_width + 2):
        pages = list(range(start, start + window_width))
        ranked.append(
            {
                "start_page": start,
                "end_page": pages[-1],
                "pages": pages,
                "score": sum(float(page_scores[page]) for page in pages),
            }
        )
    ranked.sort(key=lambda item: (-item["score"], item["start_page"]))

    selected: list[dict[str, Any]] = []
    occupied: set[int] = set()
    for window in ranked:
        if occupied.isdisjoint(window["pages"]):
            selected.append({"rank": len(selected) + 1, **window})
            occupied.update(window["pages"])
            if len(selected) == window_count:
                break
    if len(selected) != min(window_count, page_count // window_width):
        raise RuntimeError("could not select the expected number of non-overlapping windows")
    return selected


def select_anchor_centered_windows(
    page_scores: dict[int, float],
    ranked_pages: Sequence[int],
    *,
    page_count: int,
    seed_top_k: int = 10,
    window_width: int = 3,
    window_count: int = 3,
) -> list[dict[str, Any]]:
    """Build symmetric windows around BM25 seeds, then select by window sum."""
    if window_width % 2 == 0:
        raise ValueError("anchor-centered window_width must be odd")
    if seed_top_k < 1 or len(ranked_pages) < seed_top_k:
        raise ValueError("ranked_pages contains fewer pages than seed_top_k")
    if set(page_scores) != set(range(1, page_count + 1)):
        raise ValueError("page_scores must cover every physical page exactly once")
    half = window_width // 2
    last_start = page_count - window_width + 1
    if last_start < 1:
        raise ValueError("window_width cannot exceed page_count")

    candidates_by_start: dict[int, dict[str, Any]] = {}
    for seed in ranked_pages[:seed_top_k]:
        if not 1 <= seed <= page_count:
            raise ValueError("ranked page is outside the document")
        start = max(1, min(seed - half, last_start))
        pages = list(range(start, start + window_width))
        candidates_by_start.setdefault(
            start,
            {
                "start_page": start,
                "end_page": pages[-1],
                "pages": pages,
                "score": sum(float(page_scores[page]) for page in pages),
                "anchor_pages": [],
            },
        )["anchor_pages"].append(seed)

    ranked = sorted(
        candidates_by_start.values(),
        key=lambda item: (-item["score"], item["start_page"]),
    )
    selected: list[dict[str, Any]] = []
    occupied: set[int] = set()
    for window in ranked:
        if occupied.isdisjoint(window["pages"]):
            selected.append({"rank": len(selected) + 1, **window})
            occupied.update(window["pages"])
            if len(selected) == window_count:
                break
    if len(selected) < window_count:
        raise RuntimeError("not enough non-overlapping anchor-centered windows")
    return selected


def evaluate_page_windows(
    questions: Sequence[dict[str, Any]],
    corpora: dict[str, list[Any]],
    *,
    k1: float,
    b: float,
    query_token_policy: str,
    window_width: int,
    window_count: int,
    anchor_seed_top_k: int | None = None,
) -> dict[str, Any]:
    """Generate windows without labels, then evaluate their evidence coverage."""
    if not questions:
        raise ValueError("at least one question is required")
    indexes = {
        doc_id: PageBm25Index(
            records,
            k1=k1,
            b=b,
            query_token_policy=query_token_policy,
        )
        for doc_id, records in corpora.items()
    }
    per_question: list[dict[str, Any]] = []
    for question in questions:
        doc_id = question["pdf"]["doc_id_str"]
        index = indexes.get(doc_id)
        if index is None:
            raise ValueError(f"question has no OCR corpus: {doc_id}")
        ranked_pages = index.search(question["question"], top_k=len(index.records))
        scores = {result.page: result.score for result in ranked_pages}
        if anchor_seed_top_k is None:
            windows = select_non_overlapping_windows(
                scores,
                page_count=len(index.records),
                window_width=window_width,
                window_count=window_count,
            )
        else:
            windows = select_anchor_centered_windows(
                scores,
                [result.page for result in ranked_pages],
                page_count=len(index.records),
                seed_top_k=anchor_seed_top_k,
                window_width=window_width,
                window_count=window_count,
            )
        selected_pages = [page for window in windows for page in window["pages"]]

        # Gold labels are accessed only after the window list above is frozen.
        gold_pages = sorted({evidence["page"] for evidence in question["evidences"]})
        gold = set(gold_pages)
        found = sorted(gold.intersection(selected_pages))
        per_question.append(
            {
                "question_id": question["id"],
                "doc_id": doc_id,
                "question": question["question"],
                "selected_windows": windows,
                "selected_pages": selected_pages,
                "selected_page_count": len(selected_pages),
                "gold_pages": gold_pages,
                "gold_pages_found": found,
                "any_evidence_recall": float(bool(found)),
                "complete_evidence_recall": float(len(found) == len(gold)),
                "recall": len(found) / len(gold),
            }
        )

    count = len(per_question)
    return {
        "schema_version": 1,
        "question_count": count,
        "aggregate": {
            "any_evidence_recall": sum(item["any_evidence_recall"] for item in per_question) / count,
            "complete_evidence_recall": sum(item["complete_evidence_recall"] for item in per_question) / count,
            "macro_recall": sum(item["recall"] for item in per_question) / count,
            "mean_selected_page_count": sum(item["selected_page_count"] for item in per_question) / count,
        },
        "per_question": per_question,
        "uses_gold_labels_only_after_window_selection": True,
    }


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--split-manifest", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--ocr-registry", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    inventory = _read_json(args.inventory)
    registry = _read_json(args.ocr_registry)
    config = _read_json(args.config)
    tune_questions, _ = load_tune_questions(args.benchmark, args.split_manifest)
    questions = select_inventory_questions(tune_questions, inventory)
    doc_ids = [document["doc_id"] for document in inventory["documents"]]
    corpora = load_registered_r2_corpora(registry, doc_ids, root=Path.cwd())
    retrieval = config["retrieval"]
    result = evaluate_page_windows(
        questions,
        corpora,
        k1=float(retrieval["k1"]),
        b=float(retrieval["b"]),
        query_token_policy=retrieval["query_token_policy"],
        window_width=retrieval["window_width_pages"],
        window_count=retrieval["selected_window_count"],
        anchor_seed_top_k=retrieval.get("seed_top_k"),
    )
    result["configuration"] = config
    result["inputs"] = {
        "inventory_sha256": sha256_file(args.inventory),
        "ocr_registry_sha256": sha256_file(args.ocr_registry),
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
