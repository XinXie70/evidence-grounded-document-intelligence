"""Select and build a blinded, deterministic calibration human-audit worksheet."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from .io import sha256_file, write_json


SEED = "v1-calibration-human-audit-v1"


def _order(case: dict[str, Any]) -> str:
    return hashlib.sha256(f"{SEED}:{case['pilot_id']}".encode()).hexdigest()


def select_cases(
    judge_manifest: dict[str, Any], automatic_audit: dict[str, Any]
) -> list[dict[str, Any]]:
    source = judge_manifest.get("cases")
    audit = automatic_audit.get("cases")
    if not isinstance(source, list) or not isinstance(audit, list):
        raise ValueError("both artifacts require case lists")
    by_id = {row.get("pilot_id"): row for row in audit if isinstance(row, dict)}
    if len(by_id) != len(audit):
        raise ValueError("automatic audit pilot IDs must be present and unique")
    joined = []
    for case in source:
        label = by_id.pop(case.get("pilot_id"), None)
        if label is None or label.get("question_id") != case.get("question_id"):
            raise ValueError("judge and audit identities do not match")
        joined.append({**case, "automatic": label})
    if by_id:
        raise ValueError("automatic audit contains extra cases")

    selected: dict[str, dict[str, Any]] = {}

    def add_where(predicate: Callable[[dict[str, Any]], bool], limit: int | None = None) -> None:
        candidates = sorted((case for case in joined if predicate(case)), key=_order)
        if limit is not None:
            if len(candidates) < limit:
                raise ValueError("a frozen audit stratum is smaller than its required quota")
            candidates = candidates[:limit]
        for case in candidates:
            selected[case["pilot_id"]] = case

    # Preserve all rare routes and every unanswerable case.
    add_where(lambda case: case["route"] in {"r2_scanned_document", "r3_document_global"})
    add_where(lambda case: not case["gold_is_answerable"])
    # Preserve every answered automatic failure so both judge failure modes are auditable.
    add_where(
        lambda case: case["prediction"]["status"] == "answerable"
        and not case["automatic"]["grounded_correct"]
    )
    # Sample false-abstention strata from the common routes.
    for route, quota in (("r0_text", 8), ("r1_local_visual", 4)):
        add_where(
            lambda case, route=route: case["route"] == route
            and case["gold_is_answerable"]
            and case["prediction"]["status"] == "insufficient_evidence",
            quota,
        )
    # Add grounded-success controls across route and citation-span strata.
    for route, span, quota in (
        ("r0_text", "single", 4),
        ("r0_text", "multi", 3),
        ("r1_local_visual", "single", 2),
        ("r1_local_visual", "multi", 2),
    ):
        add_where(
            lambda case, route=route, span=span: case["route"] == route
            and case["prediction"]["status"] == "answerable"
            and case["automatic"]["grounded_correct"]
            and ("single" if len(case["prediction"]["cited_pages"]) == 1 else "multi") == span,
            quota,
        )
    if len(selected) != 50:
        raise ValueError(f"frozen audit design must select exactly 50 unique cases, got {len(selected)}")
    return sorted(selected.values(), key=lambda case: case["pilot_id"])


def build_blinded_worksheet(
    selected: list[dict[str, Any]], *, judge_input_root: Path,
    questions_by_id: dict[str, str] | None = None,
) -> dict[str, Any]:
    rows = []
    for index, case in enumerate(selected, start=1):
        question = None
        evidence = []
        semantic_path = judge_input_root / case["pilot_id"] / "semantic.json"
        support_path = judge_input_root / case["pilot_id"] / "support.json"
        if semantic_path.exists():
            semantic_input = json.loads(semantic_path.read_text(encoding="utf-8"))
            question = semantic_input["question"]
        if support_path.exists():
            support_input = json.loads(support_path.read_text(encoding="utf-8"))
            question = question or support_input["question"]
            evidence = support_input["cited_evidence"]
        if question is None:
            question = case.get("question")
        if question is None and questions_by_id is not None:
            question = questions_by_id.get(case["question_id"])
        if not isinstance(question, str) or not question:
            raise ValueError(f"question text is unavailable for {case['pilot_id']}")
        rows.append({
            "audit_number": index,
            "pilot_id": case["pilot_id"],
            "question_id": case["question_id"],
            "route": case["route"],
            "question": question,
            "gold_is_answerable": case["gold_is_answerable"],
            "reference_answer": case["gold_answer"] if case["gold_is_answerable"] else None,
            "system_status": case["prediction"]["status"],
            "system_answer": case["prediction"]["answer"],
            "cited_pages": case["prediction"]["cited_pages"],
            "cited_evidence": evidence,
            "human_task_correct": None,
            "human_evidence_supported": None,
            "human_note": None,
            "user_confirmed": False,
        })
    return {
        "schema_version": 1,
        "status": "pending_independent_human_review",
        "split": "development_calibration",
        "selection_seed": SEED,
        "blinding": "automatic semantic and support judgments are omitted",
        "instructions": {
            "human_task_correct": "Does the system answer match the reference meaning? For an answerable question, abstention is false; for an unanswerable question, abstention is true.",
            "human_evidence_supported": "If the system answered, do the cited extracts support every material claim? An abstention has no answer claim and is true by rule.",
        },
        "case_count": len(rows),
        "cases": rows,
    }


def selection_summary(selected: list[dict[str, Any]]) -> dict[str, Any]:
    def span(case: dict[str, Any]) -> str:
        count = len(case["prediction"]["cited_pages"])
        return "none" if count == 0 else "single" if count == 1 else "multi"
    return {
        "route_counts": dict(sorted(Counter(case["route"] for case in selected).items())),
        "gold_answerability_counts": dict(sorted(Counter(
            "answerable" if case["gold_is_answerable"] else "unanswerable" for case in selected
        ).items())),
        "system_decision_counts": dict(sorted(Counter(
            case["prediction"]["status"] for case in selected
        ).items())),
        "citation_span_counts": dict(sorted(Counter(span(case) for case in selected).items())),
        "automatic_outcome_counts_used_only_for_stratification": dict(sorted(Counter(
            f"task_{case['automatic']['task_correct']}_support_{case['automatic']['evidence_supported']}"
            for case in selected
        ).items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judge-manifest", required=True, type=Path)
    parser.add_argument("--automatic-audit", required=True, type=Path)
    parser.add_argument("--judge-input-root", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--selection-output", required=True, type=Path)
    parser.add_argument("--worksheet-output", required=True, type=Path)
    args = parser.parse_args()
    for path in (args.selection_output, args.worksheet_output):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite immutable output: {path}")
    judge = json.loads(args.judge_manifest.read_text(encoding="utf-8"))
    audit = json.loads(args.automatic_audit.read_text(encoding="utf-8"))
    source_selection = json.loads(args.selection.read_text(encoding="utf-8"))
    questions_by_id = {
        row["question_id"]: row["question"] for row in source_selection.get("questions", [])
    }
    selected = select_cases(judge, audit)
    selection = {
        "schema_version": 1,
        "status": "frozen_before_human_labels",
        "split": "development_calibration",
        "selection_seed": SEED,
        "case_count": len(selected),
        "selected_pilot_ids": [case["pilot_id"] for case in selected],
        "summary": selection_summary(selected),
        "artifacts": {
            "judge_manifest_sha256": sha256_file(args.judge_manifest),
            "automatic_audit_sha256": sha256_file(args.automatic_audit),
        },
    }
    write_json(args.selection_output, selection)
    worksheet = build_blinded_worksheet(
        selected, judge_input_root=args.judge_input_root, questions_by_id=questions_by_id
    )
    worksheet["selection_sha256"] = sha256_file(args.selection_output)
    write_json(args.worksheet_output, worksheet)
    print(json.dumps({
        "selection_output": str(args.selection_output),
        "worksheet_output": str(args.worksheet_output),
        "case_count": len(selected),
        "summary": selection["summary"],
    }, indent=2))


if __name__ == "__main__":
    main()
