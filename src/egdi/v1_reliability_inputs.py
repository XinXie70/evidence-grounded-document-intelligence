"""Build label-free current-pipeline inputs for the V1 confidence tune gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .access import require_evaluation_split_access
from .bm25 import PageBm25Index
from .confidence_features_v1 import extract_retrieval_confidence_features
from .corpus import read_page_records_jsonl
from .dense import DenseEncoder, PageDenseIndex, SentenceTransformerBgeEncoder
from .io import sha256_file, write_json
from .multihop_windows import (
    add_non_overlapping_clause_windows,
    split_explicit_clauses,
)
from .page_window import select_anchor_centered_windows
from .reasoning_inputs import DRAFT_INSTRUCTIONS, RESPONSE_SCHEMA, EvidencePage, ReasoningInput
from .rrf import reciprocal_rank_fusion
from .text import PageRecord
from .visual_routing import (
    ROUTE_DOCUMENT_GLOBAL,
    ROUTE_LOCAL_VISUAL,
    ROUTE_SCANNED_DOCUMENT,
    ROUTE_TEXT,
)
from .visual_routing_v1 import choose_visual_route_v1


ALLOWED_SPLITS = {"development_tune", "development_calibration", "locked_test"}


def _question_view(record: dict[str, Any]) -> dict[str, str]:
    """Project a labelled selection row to inference-time fields only."""
    fields = {key: record.get(key) for key in ("pilot_id", "question_id", "doc_id", "question")}
    if any(not isinstance(value, str) or not value for value in fields.values()):
        raise ValueError("selection row is missing an inference-time identity field")
    return fields  # type: ignore[return-value]


def _reasoning_record(
    question: dict[str, str],
    records: Sequence[PageRecord],
    evidence_pages: Sequence[int],
    *,
    text_overrides: dict[int, str] | None = None,
) -> dict[str, Any]:
    lookup = {record.page: record for record in records}
    if len(lookup) != len(records):
        raise ValueError("reasoning corpus contains duplicate physical pages")
    evidence = []
    for page in evidence_pages:
        if page not in lookup:
            raise ValueError(f"evidence page is absent from reasoning corpus: {page}")
        text = lookup[page].text
        if text_overrides is not None:
            if page not in text_overrides:
                raise ValueError(f"layout-preserved OCR text is missing for page: {page}")
            text = text_overrides[page]
        evidence.append(EvidencePage(page, text))
    return ReasoningInput(
        question_id=question["question_id"],
        doc_id=question["doc_id"],
        condition="real_retrieval",
        question=question["question"],
        evidence=tuple(evidence),
        instructions=DRAFT_INSTRUCTIONS,
    ).to_experiment_record()


def _rank_r2_windows(
    index: PageBm25Index, query: str, *, window_count: int = 3
) -> tuple[list[int], list[dict[str, Any]], list[Any]]:
    ranking = index.search(query, top_k=len(index.records))
    scores = {result.page: result.score for result in ranking}
    pages = [result.page for result in ranking]

    def windows_for(text: str) -> list[dict[str, Any]]:
        ranked = index.search(text, top_k=len(index.records))
        ranked_scores = {result.page: result.score for result in ranked}
        return select_anchor_centered_windows(
            ranked_scores,
            [result.page for result in ranked],
            page_count=len(index.records),
            seed_top_k=10,
            window_width=3,
            window_count=window_count,
        )

    base = [
        {**window, "source": "full_query", "output_rank": position}
        for position, window in enumerate(
            select_anchor_centered_windows(
                scores,
                pages,
                page_count=len(index.records),
                seed_top_k=10,
                window_width=3,
                window_count=window_count,
            ),
            start=1,
        )
    ]
    clauses = split_explicit_clauses(query)
    clause_windows = [windows_for(clause) for clause in clauses] if len(clauses) > 1 else []
    selected = add_non_overlapping_clause_windows(
        base, clause_windows, maximum_supplemental_windows=1
    )
    evidence_pages = [page for window in selected for page in window["pages"]]
    return evidence_pages, selected, ranking


def build_v1_reliability_cases(
    selection_rows: Sequence[dict[str, Any]],
    native_corpora: dict[str, list[PageRecord]],
    encoder: DenseEncoder,
    *,
    visual_rankings: dict[str, dict[str, Any]],
    ocr_corpora: dict[str, list[PageRecord]],
    ocr_layout_text: dict[str, dict[int, str]] | None = None,
) -> list[dict[str, Any]]:
    """Run frozen retrieval/routing without accepting labels into the output."""
    if not selection_rows:
        raise ValueError("at least one selection row is required")
    cases = []
    seen_questions: set[str] = set()
    for raw in selection_rows:
        question = _question_view(raw)
        question_id = question["question_id"]
        doc_id = question["doc_id"]
        if question_id in seen_questions:
            raise ValueError(f"duplicate question_id: {question_id}")
        seen_questions.add(question_id)
        native = native_corpora.get(doc_id)
        if not native:
            raise ValueError(f"native corpus is missing: {doc_id}")
        route_record = choose_visual_route_v1(question["question"], native)
        route = route_record["route"]

        bm25_pages: list[int] | None = None
        bm25_scores: list[float] | None = None
        dense_pages: list[int] | None = None
        rrf_pages: list[int] | None = None
        rrf_scores: list[float] | None = None
        visual_pages: list[int] | None = None
        visual_scores: list[float] | None = None
        selected_windows: list[dict[str, Any]] = []
        reasoning_text_overrides: dict[int, str] | None = None

        if route in {ROUTE_TEXT, ROUTE_LOCAL_VISUAL}:
            bm25_results = PageBm25Index(native, k1=1.2, b=0.75).search(
                question["question"], top_k=min(10, len(native))
            )
            dense_results = PageDenseIndex(
                native, encoder, chunk_tokens=256, overlap_tokens=0
            ).search(question["question"], top_k=min(10, len(native)))
            if min(len(bm25_results), len(dense_results)) < 10:
                raise ValueError("native document has fewer than ten retrievable pages")
            bm25_pages = [result.page for result in bm25_results]
            bm25_scores = [result.score for result in bm25_results]
            dense_pages = [result.page for result in dense_results]
            fused = reciprocal_rank_fusion(
                [bm25_pages, dense_pages], rank_constant=60, top_k=10
            )
            rrf_pages = [page for page, _ in fused]
            rrf_scores = [score for _, score in fused]
            if route == ROUTE_TEXT:
                evidence_pages = rrf_pages[:3]
            else:
                visual = visual_rankings.get(question_id)
                if not isinstance(visual, dict):
                    raise ValueError(f"visual ranking is missing: {question_id}")
                if visual.get("original_rrf_pages") != rrf_pages:
                    raise ValueError(f"visual candidate provenance drift: {question_id}")
                visual_pages = visual.get("visual_reranked_pages")
                visual_scores = visual.get("visual_scores")
                if not isinstance(visual_pages, list) or not isinstance(visual_scores, list):
                    raise ValueError("visual ranking is malformed")
                evidence_pages = visual_pages[:3]
            reasoning_corpus = native
        elif route == ROUTE_SCANNED_DOCUMENT:
            reasoning_corpus = ocr_corpora.get(doc_id)  # type: ignore[assignment]
            if not reasoning_corpus:
                raise ValueError(f"orientation-recovered OCR corpus is missing: {doc_id}")
            index = PageBm25Index(
                reasoning_corpus,
                k1=1.2,
                b=0.75,
                query_token_policy="deduplicate_preserve_order",
            )
            evidence_pages, selected_windows, bm25_results = _rank_r2_windows(
                index, question["question"]
            )
            bm25_pages = [result.page for result in bm25_results]
            bm25_scores = [result.score for result in bm25_results]
            if ocr_layout_text is None or doc_id not in ocr_layout_text:
                raise ValueError(f"layout-preserved OCR text is missing: {doc_id}")
            reasoning_text_overrides = ocr_layout_text[doc_id]
        elif route == ROUTE_DOCUMENT_GLOBAL:
            reasoning_corpus = native
            evidence_pages = []
        else:  # pragma: no cover - router owns the closed route vocabulary
            raise AssertionError(f"unsupported route: {route}")

        features = extract_retrieval_confidence_features(
            question_id=question_id,
            doc_id=doc_id,
            query=question["question"],
            records=reasoning_corpus,
            bm25_pages=bm25_pages,
            bm25_scores=bm25_scores,
            dense_pages=dense_pages,
            rrf_pages=rrf_pages,
            rrf_scores=rrf_scores,
            evidence_pages=evidence_pages,
            route=route,
            visual_pages=visual_pages,
            visual_scores=visual_scores,
        )
        cases.append(
            {
                "pilot_id": question["pilot_id"],
                "question_id": question_id,
                "doc_id": doc_id,
                "route": route,
                "route_record": route_record,
                "evidence_pages": evidence_pages,
                "selected_windows": selected_windows,
                "retrieval": {
                    "bm25_pages": bm25_pages,
                    "bm25_scores": bm25_scores,
                    "dense_pages": dense_pages,
                    "rrf_pages": rrf_pages,
                    "rrf_scores": rrf_scores,
                    "visual_pages": visual_pages,
                    "visual_scores": visual_scores,
                },
                "confidence_features": features,
                "paid_request_required": route != ROUTE_DOCUMENT_GLOBAL,
                "reasoning_input": _reasoning_record(
                    question,
                    reasoning_corpus,
                    evidence_pages,
                    text_overrides=reasoning_text_overrides,
                ),
            }
        )
    return cases


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_layout_text_directory(path: Path, *, expected_pages: int) -> dict[int, str]:
    """Load one immutable page-per-file OCR layout directory."""
    if not path.is_dir():
        raise FileNotFoundError(path)
    result: dict[int, str] = {}
    for file_path in sorted(path.glob("page-*.txt")):
        suffix = file_path.stem.removeprefix("page-")
        if not suffix.isdigit():
            raise ValueError(f"layout OCR filename has no numeric page: {file_path}")
        page = int(suffix)
        if page in result:
            raise ValueError(f"duplicate layout OCR page: {page}")
        result[page] = file_path.read_text(encoding="utf-8")
    if set(result) != set(range(1, expected_pages + 1)):
        raise ValueError("layout OCR directory does not cover every physical page")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--page-records-dir", required=True, type=Path)
    parser.add_argument("--visual-rankings", required=True, type=Path)
    parser.add_argument("--ocr-registry", required=True, type=Path)
    parser.add_argument("--model-cache", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    manifest_path = args.output_dir / "manifest.json"
    if manifest_path.exists():
        raise FileExistsError(f"refusing to overwrite immutable output: {manifest_path}")

    selection = _read_json(args.selection)
    split = selection.get("split")
    if split not in ALLOWED_SPLITS:
        raise ValueError("unknown selection split")
    require_evaluation_split_access(split)
    if selection.get("contains_gold_or_answer_labels") is not False:
        raise ValueError("selection must explicitly exclude gold and answer labels")
    rows = selection.get("questions")
    if not isinstance(rows, list) or not rows:
        raise ValueError("selection must contain questions")
    safe_questions = [_question_view(row) for row in rows]
    native_corpora = {
        item["doc_id"]: read_page_records_jsonl(
            args.page_records_dir / f"{item['doc_id']}.jsonl"
        )
        for item in safe_questions
    }
    visual_artifact = _read_json(args.visual_rankings)
    if visual_artifact.get("split") != split:
        raise ValueError("visual rankings split does not match selection split")
    if visual_artifact.get("contains_gold_or_answer_labels") is not False:
        raise ValueError("visual rankings are not explicitly label-free")
    visual_by_id = {
        item["question_id"]: item for item in visual_artifact.get("rankings", [])
    }
    registry = _read_json(args.ocr_registry)
    registry_by_doc = {item["doc_id"]: item for item in registry.get("documents", [])}
    ocr_corpora = {}
    ocr_layout_text = {}
    for item in safe_questions:
        route = choose_visual_route_v1(
            item["question"], native_corpora[item["doc_id"]]
        )["route"]
        if route == ROUTE_SCANNED_DOCUMENT:
            metadata = registry_by_doc.get(item["doc_id"])
            if metadata is None:
                raise ValueError(f"OCR registry entry is missing: {item['doc_id']}")
            corpus_path = Path(metadata["corpus_path"])
            if sha256_file(corpus_path) != metadata["corpus_sha256"]:
                raise ValueError(f"OCR corpus checksum mismatch: {corpus_path}")
            ocr_corpora[item["doc_id"]] = read_page_records_jsonl(corpus_path)
            ocr_layout_text[item["doc_id"]] = load_layout_text_directory(
                Path(metadata["layout_text_dir"]),
                expected_pages=len(ocr_corpora[item["doc_id"]]),
            )

    encoder = SentenceTransformerBgeEncoder(
        cache_folder=str(args.model_cache), device="cpu", local_files_only=True
    )
    cases = build_v1_reliability_cases(
        rows,
        native_corpora,
        encoder,
        visual_rankings=visual_by_id,
        ocr_corpora=ocr_corpora,
        ocr_layout_text=ocr_layout_text,
    )
    for case in cases:
        path = args.output_dir / case["pilot_id"] / "real_retrieval.json"
        write_json(path, case["reasoning_input"])
        case["reasoning_input"] = {"path": str(path), "sha256": sha256_file(path)}
    output = {
        "schema_version": 1,
        "status": "current_pipeline_inputs_frozen_before_reasoning",
        "split": split,
        "contains_gold_or_answer_labels": False,
        "case_count": len(cases),
        "paid_request_count": sum(case["paid_request_required"] for case in cases),
        "inputs": {
            "selection_sha256": sha256_file(args.selection),
            "visual_rankings_sha256": sha256_file(args.visual_rankings),
            "ocr_registry_sha256": sha256_file(args.ocr_registry),
        },
        "cases": cases,
    }
    write_json(manifest_path, output)
    print(
        json.dumps(
            {
                "output": str(manifest_path),
                "output_sha256": sha256_file(manifest_path),
                "case_count": len(cases),
                "paid_request_count": output["paid_request_count"],
                "routes": {
                    route: sum(case["route"] == route for case in cases)
                    for route in (ROUTE_TEXT, ROUTE_LOCAL_VISUAL, ROUTE_SCANNED_DOCUMENT, ROUTE_DOCUMENT_GLOBAL)
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
