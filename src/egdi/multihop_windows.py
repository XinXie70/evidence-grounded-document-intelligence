"""Add one bounded clause-derived window for explicitly segmented questions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .bm25 import PageBm25Index
from .io import sha256_file, write_json
from .page_window import select_anchor_centered_windows
from .r2_evaluate import load_registered_r2_corpora, select_inventory_questions
from .tune_baseline import load_tune_questions


EXPLICIT_CLAUSE_SEPARATOR = "—"


def split_explicit_clauses(
    question: str, *, separator: str = EXPLICIT_CLAUSE_SEPARATOR
) -> list[str]:
    """Split only on a frozen explicit delimiter; never infer latent subquestions."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a non-empty string")
    if not isinstance(separator, str) or not separator:
        raise ValueError("separator must be a non-empty string")
    parts = [part.strip(" ,") for part in question.split(separator)]
    if len(parts) == 1:
        return [question.strip()]
    if any(not part for part in parts):
        raise ValueError("explicit clause separator produced an empty clause")
    return parts


def add_non_overlapping_clause_windows(
    base_windows: Sequence[dict[str, Any]],
    clause_window_sets: Sequence[Sequence[dict[str, Any]]],
    *,
    maximum_supplemental_windows: int = 1,
) -> list[dict[str, Any]]:
    """Append the earliest ranked, fully novel clause window under a hard cap."""
    if (
        isinstance(maximum_supplemental_windows, bool)
        or not isinstance(maximum_supplemental_windows, int)
        or maximum_supplemental_windows < 0
    ):
        raise ValueError("maximum_supplemental_windows must be a non-negative integer")
    selected = [dict(window) for window in base_windows]
    if maximum_supplemental_windows == 0:
        return selected
    occupied = {page for window in selected for page in window["pages"]}
    supplements = 0
    for clause_index, windows in enumerate(clause_window_sets, start=1):
        for window in windows:
            if occupied.isdisjoint(window["pages"]):
                selected.append(
                    {
                        **window,
                        "source": "explicit_clause",
                        "clause_index": clause_index,
                        "output_rank": len(selected) + 1,
                    }
                )
                occupied.update(window["pages"])
                supplements += 1
                break
        if supplements == maximum_supplemental_windows:
            break
    return selected


def _rank_windows(
    index: PageBm25Index,
    query: str,
    *,
    seed_top_k: int,
    window_width: int,
    window_count: int,
) -> list[dict[str, Any]]:
    ranking = index.search(query, top_k=len(index.records))
    windows = select_anchor_centered_windows(
        {result.page: result.score for result in ranking},
        [result.page for result in ranking],
        page_count=len(index.records),
        seed_top_k=seed_top_k,
        window_width=window_width,
        window_count=window_count,
    )
    return windows


def evaluate_multihop_windows(
    questions: Sequence[dict[str, Any]],
    corpora: dict[str, list[Any]],
    *,
    k1: float,
    b: float,
    query_token_policy: str,
    seed_top_k: int,
    window_width: int,
    base_window_count: int,
    maximum_supplemental_windows: int,
    separator: str = EXPLICIT_CLAUSE_SEPARATOR,
) -> dict[str, Any]:
    """Select all windows without labels, then measure evidence coverage."""
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
    evaluated: list[dict[str, Any]] = []
    for question in questions:
        doc_id = question["pdf"]["doc_id_str"]
        index = indexes[doc_id]
        base_windows = [
            {**window, "source": "full_query", "output_rank": position}
            for position, window in enumerate(
                _rank_windows(
                    index,
                    question["question"],
                    seed_top_k=seed_top_k,
                    window_width=window_width,
                    window_count=base_window_count,
                ),
                start=1,
            )
        ]
        clauses = split_explicit_clauses(question["question"], separator=separator)
        clause_windows = []
        if len(clauses) > 1:
            clause_windows = [
                _rank_windows(
                    index,
                    clause,
                    seed_top_k=seed_top_k,
                    window_width=window_width,
                    window_count=base_window_count,
                )
                for clause in clauses
            ]
        windows = add_non_overlapping_clause_windows(
            base_windows,
            clause_windows,
            maximum_supplemental_windows=maximum_supplemental_windows,
        )
        selected_pages = [page for window in windows for page in window["pages"]]

        # Benchmark labels are accessed only after the candidate pages are frozen.
        gold_pages = sorted({evidence["page"] for evidence in question["evidences"]})
        gold = set(gold_pages)
        found = sorted(gold.intersection(selected_pages))
        evaluated.append(
            {
                "question_id": question["id"],
                "doc_id": doc_id,
                "question": question["question"],
                "explicit_clauses": clauses if len(clauses) > 1 else [],
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

    count = len(evaluated)
    page_counts = [record["selected_page_count"] for record in evaluated]
    return {
        "schema_version": 1,
        "question_count": count,
        "aggregate": {
            "any_evidence_recall": sum(r["any_evidence_recall"] for r in evaluated)
            / count,
            "complete_evidence_recall": sum(
                r["complete_evidence_recall"] for r in evaluated
            )
            / count,
            "macro_recall": sum(r["recall"] for r in evaluated) / count,
            "selected_page_count": {
                "minimum": min(page_counts),
                "maximum": max(page_counts),
                "mean": sum(page_counts) / count,
            },
        },
        "per_question": evaluated,
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
    result = evaluate_multihop_windows(
        questions,
        corpora,
        k1=float(retrieval["k1"]),
        b=float(retrieval["b"]),
        query_token_policy=retrieval["query_token_policy"],
        seed_top_k=retrieval["seed_top_k"],
        window_width=retrieval["window_width_pages"],
        base_window_count=retrieval["base_window_count"],
        maximum_supplemental_windows=retrieval["maximum_supplemental_windows"],
        separator=retrieval["explicit_clause_separator"],
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
