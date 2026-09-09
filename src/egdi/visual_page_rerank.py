"""Label-free layout-aware reranking within a frozen RRF page pool."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence

from .corpus import read_page_records_jsonl
from .io import sha256_file, write_json
from .scoring import aggregate_page_scores, score_evidence_pages
from .visual_routing import ROUTE_LOCAL_VISUAL
from .visual_routing_v1 import choose_visual_route_v1


RASTER_CUES = {"image", "illustration"}
TABLE_CUES = {"table"}
VECTOR_CUES = {"bar chart", "chart", "figure", "diagram", "graph", "map"}
SUPPORTED_CUES = RASTER_CUES | TABLE_CUES | VECTOR_CUES
EVALUATION_KS = (1, 3, 5, 10)


def extract_candidate_layout_signals(
    pdf_path: Path, candidate_pages: Sequence[int]
) -> dict[int, dict[str, int]]:
    """Extract PDF-native visual signals for requested physical pages only."""
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)
    if not candidate_pages or any(
        isinstance(page, bool) or not isinstance(page, int) or page < 1
        for page in candidate_pages
    ):
        raise ValueError("candidate_pages must contain positive integers")
    if len(candidate_pages) != len(set(candidate_pages)):
        raise ValueError("candidate_pages must be unique")

    try:
        import pdfplumber
    except ImportError as error:  # pragma: no cover - environment-specific
        raise RuntimeError("pdfplumber is required for layout signal extraction") from error

    signals: dict[int, dict[str, int]] = {}
    with pdfplumber.open(pdf_path) as document:
        for physical_page in candidate_pages:
            if physical_page > len(document.pages):
                raise ValueError(f"candidate page exceeds PDF length: {physical_page}")
            page = document.pages[physical_page - 1]
            line_count = len(page.lines)
            rectangle_count = len(page.rects)
            curve_count = len(page.curves)
            signals[physical_page] = {
                "raster_image_count": len(page.images),
                "detected_table_count": len(page.find_tables()),
                "line_count": line_count,
                "rectangle_count": rectangle_count,
                "curve_count": curve_count,
                "vector_object_count": line_count + rectangle_count + curve_count,
            }
    return signals


def page_matches_visual_cue(cue: str, signal: dict[str, Any]) -> bool:
    """Apply the preregistered binary page-type preference."""
    if cue not in SUPPORTED_CUES:
        raise ValueError(f"unsupported visual cue: {cue}")
    required = {
        "raster_image_count",
        "detected_table_count",
        "vector_object_count",
    }
    if not required.issubset(signal):
        raise ValueError("layout signal is missing required counts")
    if any(
        isinstance(signal[key], bool)
        or not isinstance(signal[key], int)
        or signal[key] < 0
        for key in required
    ):
        raise ValueError("layout signal counts must be non-negative integers")
    if cue in TABLE_CUES:
        return signal["detected_table_count"] > 0
    if cue in RASTER_CUES:
        return signal["raster_image_count"] > 0
    return signal["raster_image_count"] > 0 or signal["vector_object_count"] > 0


def rerank_visual_candidates(
    candidate_pages: Sequence[int], cue: str, signals: dict[int, dict[str, Any]]
) -> list[int]:
    """Move cue-compatible pages first while preserving RRF order within groups."""
    if not candidate_pages or len(candidate_pages) != len(set(candidate_pages)):
        raise ValueError("candidate_pages must be non-empty and unique")
    if set(candidate_pages) != set(signals):
        raise ValueError("signals must cover exactly the candidate pages")
    preferred = {
        page: page_matches_visual_cue(cue, signals[page]) for page in candidate_pages
    }
    return sorted(candidate_pages, key=lambda page: not preferred[page])


def _aggregate(per_question: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        str(k): aggregate_page_scores(
            [
                score_evidence_pages(item["gold_pages"], item["reranked_pages"], k)
                for item in per_question
            ]
        )
        for k in EVALUATION_KS
    }


def evaluate_visual_page_rerank(
    rrf_run: dict[str, Any], *, page_records_dir: Path, pdf_root: Path
) -> dict[str, Any]:
    """Evaluate the frozen label-free reranker; gold pages are read only by scoring."""
    if rrf_run.get("split") != "development_tune":
        raise ValueError("visual rerank evaluation is restricted to development_tune")
    source_questions = rrf_run.get("per_question")
    if not isinstance(source_questions, list) or not source_questions:
        raise ValueError("RRF run must contain per_question records")

    selected: list[tuple[dict[str, Any], str]] = []
    records_by_doc: dict[str, Any] = {}
    pages_by_doc: dict[str, set[int]] = defaultdict(set)
    for item in source_questions:
        doc_id = item.get("doc_id")
        question = item.get("question")
        candidates = item.get("retrieved_pages")
        if not isinstance(doc_id, str) or not isinstance(question, str):
            raise ValueError("RRF question must contain doc_id and question")
        if not isinstance(candidates, list) or len(candidates) < 10:
            raise ValueError("RRF question must expose at least ten retrieved pages")
        if doc_id not in records_by_doc:
            records_by_doc[doc_id] = read_page_records_jsonl(
                page_records_dir / f"{doc_id}.jsonl"
            )
        route = choose_visual_route_v1(question, records_by_doc[doc_id])
        if route["route"] != ROUTE_LOCAL_VISUAL:
            continue
        cue = route["matched_signal"]
        if cue not in SUPPORTED_CUES:
            raise ValueError(f"router emitted unsupported R1 cue: {cue}")
        selected.append((item, cue))
        pages_by_doc[doc_id].update(candidates[:10])
    if not selected:
        raise ValueError("RRF run contains no R1 questions")

    signals_by_doc: dict[str, dict[int, dict[str, int]]] = {}
    pdf_hashes: dict[str, str] = {}
    for doc_id, pages in pages_by_doc.items():
        pdf_path = pdf_root / f"{doc_id}.pdf"
        ordered_pages = sorted(pages)
        signals_by_doc[doc_id] = extract_candidate_layout_signals(pdf_path, ordered_pages)
        pdf_hashes[doc_id] = sha256_file(pdf_path)

    per_question = []
    for item, cue in selected:
        doc_id = item["doc_id"]
        original = item["retrieved_pages"][:10]
        question_signals = {page: signals_by_doc[doc_id][page] for page in original}
        reranked = rerank_visual_candidates(original, cue, question_signals)
        per_question.append(
            {
                "question_id": item["question_id"],
                "question": item["question"],
                "doc_id": doc_id,
                "matched_visual_cue": cue,
                "original_rrf_pages": original,
                "reranked_pages": reranked,
                "layout_signals": question_signals,
                "gold_pages": item["gold_pages"],
                "slices": item["slices"],
            }
        )

    return {
        "schema_version": 1,
        "experiment_type": "r1_visual_page_rerank_v0",
        "split": "development_tune",
        "question_count": len(per_question),
        "runtime_uses_gold_or_answer_labels": False,
        "configuration": {
            "candidate_source": "frozen_equal_weight_bm25_dense_rrf_top10",
            "preference": "binary_cue_compatible_first",
            "within_group_order": "preserve_original_rrf_order",
            "evaluation_ks": list(EVALUATION_KS),
        },
        "source_pdf_sha256": dict(sorted(pdf_hashes.items())),
        "aggregate": _aggregate(per_question),
        "per_question": per_question,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rrf-run", required=True, type=Path)
    parser.add_argument("--page-records-dir", required=True, type=Path)
    parser.add_argument("--pdf-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable output: {args.output}")
    rrf_run = json.loads(args.rrf_run.read_text(encoding="utf-8"))
    result = evaluate_visual_page_rerank(
        rrf_run,
        page_records_dir=args.page_records_dir,
        pdf_root=args.pdf_root,
    )
    result["rrf_run_sha256"] = sha256_file(args.rrf_run)
    write_json(args.output, result)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "output_sha256": sha256_file(args.output),
                "question_count": result["question_count"],
                "aggregate": result["aggregate"],
                "paid_api_used": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
