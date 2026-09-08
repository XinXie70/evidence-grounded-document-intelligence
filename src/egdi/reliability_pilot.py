"""Select a deterministic, document-unique Reliability pilot from development_tune."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from .access import load_records
from .io import sha256_file, write_json


SEED = "day4-reliability-pilot-v0-2026-09-04"
VISUAL_TYPES = {"chart", "figure", "figure_title", "vision_footnote"}

SLOTS: tuple[dict[str, str], ...] = (
    {"id": "c_text_single", "kind": "answerable", "band": "complete", "bucket": "text", "span": "single", "status": "ok"},
    {"id": "c_text_multi", "kind": "answerable", "band": "complete", "bucket": "text", "span": "multi", "status": "ok"},
    {"id": "c_table_single", "kind": "answerable", "band": "complete", "bucket": "table", "span": "single", "status": "ok"},
    {"id": "c_table_multi", "kind": "answerable", "band": "complete", "bucket": "table", "span": "multi", "status": "ok"},
    {"id": "c_mixed_multi", "kind": "answerable", "band": "complete", "bucket": "mixed", "span": "multi", "status": "ok"},
    {"id": "c_visual_single", "kind": "answerable", "band": "complete", "bucket": "visual", "span": "single", "status": "ok"},
    {"id": "p_text_multi_1", "kind": "answerable", "band": "partial", "bucket": "text", "span": "multi", "status": "ok"},
    {"id": "p_text_multi_2", "kind": "answerable", "band": "partial", "bucket": "text", "span": "multi", "status": "ok"},
    {"id": "p_table_multi_1", "kind": "answerable", "band": "partial", "bucket": "table", "span": "multi", "status": "ok"},
    {"id": "p_table_multi_2", "kind": "answerable", "band": "partial", "bucket": "table", "span": "multi", "status": "ok"},
    {"id": "p_mixed_multi_low", "kind": "answerable", "band": "partial", "bucket": "mixed", "span": "multi", "status": "low_text"},
    {"id": "p_visual_multi", "kind": "answerable", "band": "partial", "bucket": "visual", "span": "multi", "status": "ok"},
    {"id": "n_text_multi_1", "kind": "answerable", "band": "none", "bucket": "text", "span": "multi", "status": "ok"},
    {"id": "n_text_multi_2", "kind": "answerable", "band": "none", "bucket": "text", "span": "multi", "status": "ok"},
    {"id": "n_table_single", "kind": "answerable", "band": "none", "bucket": "table", "span": "single", "status": "ok"},
    {"id": "n_table_multi_missing", "kind": "answerable", "band": "none", "bucket": "table", "span": "multi", "status": "text_layer_missing"},
    {"id": "n_mixed_single_missing", "kind": "answerable", "band": "none", "bucket": "mixed", "span": "single", "status": "text_layer_missing"},
    {"id": "n_visual_multi", "kind": "answerable", "band": "none", "bucket": "visual", "span": "multi", "status": "ok"},
    {"id": "u_low_1", "kind": "unanswerable", "signal": "low"},
    {"id": "u_low_2", "kind": "unanswerable", "signal": "low"},
    {"id": "u_mid_1", "kind": "unanswerable", "signal": "mid"},
    {"id": "u_mid_2", "kind": "unanswerable", "signal": "mid"},
    {"id": "u_mid_3", "kind": "unanswerable", "signal": "mid"},
    {"id": "u_high_1", "kind": "unanswerable", "signal": "high"},
)


def _retrieval_band(record: dict[str, Any]) -> str:
    scores = record.get("scores", {}).get("3", {})
    if scores.get("complete_evidence_recall") == 1:
        return "complete"
    if scores.get("any_evidence_recall") == 1:
        return "partial"
    if scores.get("any_evidence_recall") == 0:
        return "none"
    raise ValueError("retrieval record has invalid Top-3 scores")


def _evidence_bucket(raw_type: str) -> str:
    return "visual" if raw_type in VISUAL_TYPES else raw_type


def _signal_band(score: float) -> str:
    if score <= 14.608:
        return "low"
    if score < 28.046:
        return "mid"
    return "high"


def _priority(slot_id: str, question_id: str) -> str:
    value = f"{SEED}|{slot_id}|{question_id}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _matches(slot: dict[str, str], candidate: dict[str, Any]) -> bool:
    if slot["kind"] != candidate["kind"]:
        return False
    if slot["kind"] == "unanswerable":
        return slot["signal"] == candidate["bm25_signal_band"]
    return all(
        slot[key] == candidate[value_key]
        for key, value_key in (
            ("band", "retrieval_band"),
            ("bucket", "evidence_bucket"),
            ("span", "page_span"),
            ("status", "gold_text_status"),
        )
    )


def select_reliability_pilot(
    questions: dict[str, dict[str, Any]],
    retrieval_records: list[dict[str, Any]],
    feature_records: list[dict[str, Any]],
    *,
    tune_question_ids: set[str],
    excluded_question_ids: set[str],
) -> list[dict[str, Any]]:
    """Return the first deterministic assignment satisfying the frozen v0 slots."""
    features = {item["question_id"]: item for item in feature_records}
    retrieval = {item["question_id"]: item for item in retrieval_records}
    candidates: list[dict[str, Any]] = []

    for question_id in sorted(tune_question_ids - excluded_question_ids):
        question = questions.get(question_id)
        feature = features.get(question_id)
        if question is None or feature is None:
            raise ValueError(f"missing tune question or feature record: {question_id}")
        answer = question.get("answer")
        pdf = question.get("pdf")
        if not isinstance(answer, dict) or not isinstance(answer.get("is_answerable"), bool):
            raise ValueError(f"invalid answerability metadata: {question_id}")
        if not isinstance(pdf, dict) or not isinstance(pdf.get("doc_id_str"), str):
            raise ValueError(f"invalid document metadata: {question_id}")
        base = {
            "question_id": question_id,
            "doc_id": pdf["doc_id_str"],
            "question": question["question"],
            "bm25_top1_score": feature["bm25_top1_score"],
            "bm25_top1_top2_margin": feature["bm25_top1_top2_margin"],
            "bm25_top3_pages": feature["top3_pages"],
            "top3_extraction_status_counts": feature["top3_extraction_status_counts"],
        }
        if answer["is_answerable"]:
            result = retrieval.get(question_id)
            if result is None:
                raise ValueError(f"answerable question lacks retrieval evaluation: {question_id}")
            slices = result["slices"]
            raw_type = slices["evidence_type"]
            candidates.append({
                **base,
                "kind": "answerable",
                "retrieval_band": _retrieval_band(result),
                "evidence_type": raw_type,
                "evidence_bucket": _evidence_bucket(raw_type),
                "page_span": slices["page_span"],
                "gold_text_status": slices["gold_text_status"],
                "oracle_pages": result["gold_pages"],
            })
        else:
            candidates.append({
                **base,
                "kind": "unanswerable",
                "bm25_signal_band": _signal_band(feature["bm25_top1_score"]),
                "oracle_pages": [],
            })

    candidates_by_slot = {
        slot["id"]: sorted(
            (item for item in candidates if _matches(slot, item)),
            key=lambda item: (_priority(slot["id"], item["question_id"]), item["question_id"]),
        )
        for slot in SLOTS
    }
    empty_slots = [slot_id for slot_id, items in candidates_by_slot.items() if not items]
    if empty_slots:
        raise ValueError(f"pilot slots have no candidates: {empty_slots}")

    def search(
        remaining: tuple[str, ...],
        used_questions: frozenset[str],
        used_docs: frozenset[str],
        assignments: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]] | None:
        if not remaining:
            return assignments
        eligible = {
            slot_id: [
                item for item in candidates_by_slot[slot_id]
                if item["question_id"] not in used_questions and item["doc_id"] not in used_docs
            ]
            for slot_id in remaining
        }
        if any(not items for items in eligible.values()):
            return None
        slot_id = min(remaining, key=lambda item: (len(eligible[item]), item))
        next_remaining = tuple(item for item in remaining if item != slot_id)
        for candidate in eligible[slot_id]:
            found = search(
                next_remaining,
                used_questions | {candidate["question_id"]},
                used_docs | {candidate["doc_id"]},
                {**assignments, slot_id: candidate},
            )
            if found is not None:
                return found
        return None

    assignment = search(
        tuple(slot["id"] for slot in SLOTS), frozenset(), frozenset(), {}
    )
    if assignment is None:
        raise ValueError("no document-unique assignment satisfies the frozen pilot slots")

    selected = []
    for index, slot in enumerate(SLOTS, start=1):
        candidate = assignment[slot["id"]]
        selected.append({
            "pilot_id": f"pilot_{index:02d}",
            "slot_id": slot["id"],
            **candidate,
        })
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--split-manifest", required=True, type=Path)
    parser.add_argument("--retrieval-results", required=True, type=Path)
    parser.add_argument("--confidence-features", required=True, type=Path)
    parser.add_argument("--smoke-selection", required=True, type=Path)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable selection: {args.output}")

    split_manifest = json.loads(args.split_manifest.read_text(encoding="utf-8"))
    tune_ids = set(split_manifest["development_tune"]["question_ids"])
    questions = {
        item["id"]: item for item in load_records(args.benchmark, split="dev")
        if item["id"] in tune_ids
    }
    retrieval = json.loads(args.retrieval_results.read_text(encoding="utf-8"))
    features = json.loads(args.confidence_features.read_text(encoding="utf-8"))
    smoke = json.loads(args.smoke_selection.read_text(encoding="utf-8"))
    excluded_ids = {item["question_id"] for item in smoke["questions"]}
    selected = select_reliability_pilot(
        questions,
        retrieval["per_question"],
        features["records"],
        tune_question_ids=tune_ids,
        excluded_question_ids=excluded_ids,
    )
    output = {
        "schema_version": 1,
        "status": "frozen_for_reliability_pilot_v0",
        "split": "development_tune",
        "seed": SEED,
        "question_count": len(selected),
        "document_count": len({item["doc_id"] for item in selected}),
        "excluded_smoke_question_count": len(excluded_ids),
        "source_sha256": {
            "split_manifest": sha256_file(args.split_manifest),
            "retrieval_results": sha256_file(args.retrieval_results),
            "confidence_features": sha256_file(args.confidence_features),
            "smoke_selection": sha256_file(args.smoke_selection),
            "protocol": sha256_file(args.protocol),
        },
        "questions": selected,
    }
    serialized = json.dumps(output, ensure_ascii=False)
    for forbidden in ("answer_text", '"facts"', '"evidences"'):
        if forbidden in serialized:
            raise ValueError(f"forbidden answer-bearing field in selection: {forbidden}")
    write_json(args.output, output)
    print(json.dumps({
        "output": str(args.output),
        "output_sha256": sha256_file(args.output),
        "question_count": output["question_count"],
        "document_count": output["document_count"],
        "answerable_count": sum(item["kind"] == "answerable" for item in selected),
        "unanswerable_count": sum(item["kind"] == "unanswerable" for item in selected),
    }, indent=2))


if __name__ == "__main__":
    main()
