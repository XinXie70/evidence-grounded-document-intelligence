"""Label-free confidence features for the frozen V1 retrieval and reasoning path."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any, Sequence

from .text import PageRecord, tokenize_for_bm25
from .visual_routing import (
    ROUTE_DOCUMENT_GLOBAL,
    ROUTE_LOCAL_VISUAL,
    ROUTE_SCANNED_DOCUMENT,
    ROUTE_TEXT,
)


ROUTES = {ROUTE_TEXT, ROUTE_LOCAL_VISUAL, ROUTE_SCANNED_DOCUMENT, ROUTE_DOCUMENT_GLOBAL}
FORBIDDEN_KEYS = {
    "answer",
    "answer_text",
    "benchmark_is_answerable",
    "evidences",
    "facts",
    "gold_pages",
    "task_correct",
    "grounded_correct",
    "evidence_sufficient",
    "oracle_pages",
}


def contains_forbidden_confidence_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            key in FORBIDDEN_KEYS or contains_forbidden_confidence_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(contains_forbidden_confidence_key(item) for item in value)
    return False


def _pages(values: Any, field: str, *, allow_empty: bool = False) -> list[int]:
    if not isinstance(values, list) or (not values and not allow_empty):
        raise ValueError(f"{field} must be {'a' if allow_empty else 'a non-empty'} list")
    if any(isinstance(page, bool) or not isinstance(page, int) or page < 1 for page in values):
        raise ValueError(f"{field} must contain positive integer pages")
    if len(values) != len(set(values)):
        raise ValueError(f"{field} must contain unique pages")
    return values


def _scores(values: Any, field: str, expected: int) -> list[float]:
    if not isinstance(values, list) or len(values) != expected:
        raise ValueError(f"{field} must align with its page ranking")
    result = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{field} must contain finite numeric values")
        result.append(float(value))
    if any(left < right for left, right in zip(result, result[1:])):
        raise ValueError(f"{field} must follow descending retrieval order")
    return result


def _agreement(left: Sequence[int], right: Sequence[int], k: int) -> float:
    return len(set(left[:k]) & set(right[:k])) / k


def _normalized_margin(scores: Sequence[float]) -> float:
    if len(scores) < 2:
        raise ValueError("at least two scores are required for a margin")
    scale = max(abs(scores[0]), abs(scores[1]), 1e-12)
    return (scores[0] - scores[1]) / scale


def extract_retrieval_confidence_features(
    *,
    question_id: str,
    doc_id: str,
    query: str,
    records: Sequence[PageRecord],
    bm25_pages: list[int] | None,
    bm25_scores: list[float] | None,
    dense_pages: list[int] | None,
    rrf_pages: list[int] | None,
    rrf_scores: list[float] | None,
    evidence_pages: list[int],
    route: str,
    visual_pages: list[int] | None = None,
    visual_scores: list[float] | None = None,
) -> dict[str, Any]:
    """Extract raw inference-time signals without labels or a learned threshold."""
    if not isinstance(question_id, str) or not question_id:
        raise ValueError("question_id must be a non-empty string")
    if not isinstance(doc_id, str) or not doc_id:
        raise ValueError("doc_id must be a non-empty string")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    query_tokens = tokenize_for_bm25(query)
    if not query_tokens:
        raise ValueError("query must contain at least one token")
    if route not in ROUTES:
        raise ValueError("route is not part of the frozen R0-R3 policy")
    if not records or any(record.doc_id != doc_id for record in records):
        raise ValueError("records must be non-empty and match doc_id")
    record_by_page = {record.page: record for record in records}
    if len(record_by_page) != len(records):
        raise ValueError("records must have unique physical pages")

    if route in {ROUTE_TEXT, ROUTE_LOCAL_VISUAL}:
        bm25 = _pages(bm25_pages, "bm25_pages")
        dense = _pages(dense_pages, "dense_pages")
        rrf = _pages(rrf_pages, "rrf_pages")
        if min(len(bm25), len(dense), len(rrf)) < 10:
            raise ValueError("native retrieval rankings must contain at least ten pages")
        bm25_values = _scores(bm25_scores, "bm25_scores", len(bm25))
        rrf_values = _scores(rrf_scores, "rrf_scores", len(rrf))
    elif route == ROUTE_SCANNED_DOCUMENT:
        bm25 = _pages(bm25_pages, "bm25_pages")
        if len(bm25) < 10:
            raise ValueError("OCR BM25 ranking must contain at least ten pages")
        bm25_values = _scores(bm25_scores, "bm25_scores", len(bm25))
        if any(value is not None for value in (dense_pages, rrf_pages, rrf_scores)):
            raise ValueError("scanned-document route must not fabricate dense or RRF signals")
        dense = []
        rrf = []
        rrf_values = []
    else:
        if any(
            value is not None
            for value in (bm25_pages, bm25_scores, dense_pages, rrf_pages, rrf_scores)
        ):
            raise ValueError("document-global route must not contain retrieval rankings")
        bm25 = []
        dense = []
        rrf = []
        bm25_values = []
        rrf_values = []

    allow_empty = route == ROUTE_DOCUMENT_GLOBAL
    evidence = _pages(evidence_pages, "evidence_pages", allow_empty=allow_empty)
    if route != ROUTE_DOCUMENT_GLOBAL and not evidence:
        raise ValueError("non-global routes require at least one evidence page")
    if any(page not in record_by_page for page in evidence):
        raise ValueError("evidence page is missing from the document corpus")
    if route in {ROUTE_TEXT, ROUTE_LOCAL_VISUAL} and any(
        page not in rrf[:10] for page in evidence
    ):
        raise ValueError("native-route evidence pages must come from the frozen RRF Top-10 pool")

    if route == ROUTE_LOCAL_VISUAL:
        visual = _pages(visual_pages, "visual_pages")
        visual_values = _scores(visual_scores, "visual_scores", len(visual))
        if visual[: len(evidence)] != evidence:
            raise ValueError("visual evidence pages must be a prefix of the visual ranking")
        if set(visual) != set(rrf[: len(visual)]):
            raise ValueError("visual ranking must preserve the RRF candidate set")
        visual_margin = _normalized_margin(visual_values)
        visual_top3_rrf_retention = len(set(visual[:3]) & set(rrf[:3])) / 3
        rrf_positions = {page: index for index, page in enumerate(rrf[:10], start=1)}
        visual_mean_absolute_displacement = sum(
            abs(index - rrf_positions[page])
            for index, page in enumerate(visual, start=1)
        ) / len(visual)
    else:
        if visual_pages is not None or visual_scores is not None:
            raise ValueError("visual signals are allowed only on the local-visual route")
        visual_margin = None
        visual_top3_rrf_retention = None
        visual_mean_absolute_displacement = None
        if route == ROUTE_TEXT and rrf[: len(evidence)] != evidence:
            raise ValueError("text-route evidence pages must be a prefix of the RRF ranking")

    unique_query_tokens = set(query_tokens)
    evidence_token_sets = [set(tokenize_for_bm25(record_by_page[page].text)) for page in evidence]
    covered_tokens = set().union(*evidence_token_sets) if evidence_token_sets else set()
    status_counts = Counter(record_by_page[page].extraction_status for page in evidence)
    final_top3 = evidence[:3]
    dual_support = (
        sum(page in bm25[:10] and page in dense[:10] for page in final_top3)
        if dense
        else None
    )
    output = {
        "question_id": question_id,
        "doc_id": doc_id,
        "route": route,
        "evidence_page_count": len(evidence),
        "query_unique_token_count": len(unique_query_tokens),
        "query_token_coverage_ratio": len(unique_query_tokens & covered_tokens) / len(unique_query_tokens),
        "evidence_token_count": sum(len(tokens) for tokens in evidence_token_sets),
        "bm25_dense_agreement_at_3": _agreement(bm25, dense, 3) if dense else None,
        "bm25_dense_agreement_at_5": _agreement(bm25, dense, 5) if dense else None,
        "bm25_dense_agreement_at_10": _agreement(bm25, dense, 10) if dense else None,
        "final_top3_dual_support_rate": (
            dual_support / len(final_top3) if dual_support is not None and final_top3 else None
        ),
        "bm25_top1_score": bm25_values[0] if bm25_values else None,
        "bm25_normalized_top1_top2_margin": (
            _normalized_margin(bm25_values) if bm25_values else None
        ),
        "rrf_top1_score": rrf_values[0] if rrf_values else None,
        "rrf_normalized_top1_top2_margin": (
            _normalized_margin(rrf_values) if rrf_values else None
        ),
        "evidence_extraction_status_counts": {
            "ok": status_counts.get("ok", 0),
            "low_text": status_counts.get("low_text", 0),
            "text_layer_missing": status_counts.get("text_layer_missing", 0),
        },
        "visual_normalized_top1_top2_margin": visual_margin,
        "visual_top3_rrf_retention_rate": visual_top3_rrf_retention,
        "visual_mean_absolute_rank_displacement": visual_mean_absolute_displacement,
    }
    if contains_forbidden_confidence_key(output):
        raise ValueError("confidence feature record contains a forbidden evaluation field")
    return output


def attach_postgeneration_confidence_features(
    retrieval_features: dict[str, Any], reasoning_result: dict[str, Any]
) -> dict[str, Any]:
    """Attach only contract and citation signals, never answer text or correctness labels."""
    if contains_forbidden_confidence_key(retrieval_features):
        raise ValueError("retrieval features contain a forbidden evaluation field")
    if reasoning_result.get("question_id") != retrieval_features.get("question_id"):
        raise ValueError("reasoning result question identity drift")
    output = reasoning_result.get("output")
    validation = reasoning_result.get("validation")
    if not isinstance(output, dict) or not isinstance(validation, dict):
        raise ValueError("reasoning result requires output and validation objects")
    status = output.get("status")
    citations = output.get("cited_pages")
    if status not in {"answerable", "insufficient_evidence"}:
        raise ValueError("reasoning response status is invalid")
    cited = _pages(citations, "cited_pages", allow_empty=True)
    evidence_count = retrieval_features.get("evidence_page_count")
    if isinstance(evidence_count, bool) or not isinstance(evidence_count, int) or evidence_count < 0:
        raise ValueError("retrieval feature evidence_page_count is invalid")
    contract_valid = validation.get("valid")
    citations_within = validation.get("citations_within_supplied_context")
    if not isinstance(contract_valid, bool) or not isinstance(citations_within, bool):
        raise ValueError("reasoning validation flags must be boolean")
    citations_nonempty = bool(cited)
    policy_eligible = status == "answerable" and contract_valid and citations_within and citations_nonempty
    result = {
        **retrieval_features,
        "response_status": status,
        "response_contract_valid": contract_valid,
        "citations_within_supplied_context": citations_within,
        "citation_count": len(cited),
        "citation_to_evidence_ratio": len(cited) / evidence_count if evidence_count else 0.0,
        "policy_eligible": policy_eligible,
    }
    if contains_forbidden_confidence_key(result):
        raise ValueError("post-generation features contain a forbidden evaluation field")
    return result
