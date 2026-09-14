"""Summarize agreement between blinded human labels and automatic calibration judges."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .io import sha256_file, write_json


def build_agreement_report(
    worksheet: dict[str, Any], automatic_audit: dict[str, Any]
) -> dict[str, Any]:
    cases = worksheet.get("cases")
    automatic_cases = automatic_audit.get("cases")
    if not isinstance(cases, list) or not isinstance(automatic_cases, list):
        raise ValueError("worksheet and automatic audit require case lists")
    if not all(case.get("user_confirmed") is True for case in cases):
        raise ValueError("every selected case must have a confirmed human task label")

    automatic_by_id = {case.get("pilot_id"): case for case in automatic_cases}
    assisted = worksheet.get("assisted_adjudication", {})
    assisted_labels = assisted.get("evidence_support_by_audit_number", {})
    rows = []
    for case in cases:
        automatic = automatic_by_id.get(case.get("pilot_id"))
        if automatic is None or automatic.get("question_id") != case.get("question_id"):
            raise ValueError("worksheet and automatic audit identities do not match")
        task = case.get("human_task_correct")
        if not isinstance(task, bool):
            raise ValueError("confirmed task labels must be boolean")
        independent_support = case.get("human_evidence_supported")
        if independent_support is not None and not isinstance(independent_support, bool):
            raise ValueError("human evidence labels must be boolean or null")
        assisted_support = assisted_labels.get(str(case["audit_number"]))
        if assisted_support is not None and not isinstance(assisted_support, bool):
            raise ValueError("assisted evidence labels must be boolean")
        if independent_support is None and assisted_support is None:
            raise ValueError("every uncertain support label requires assisted adjudication")
        if independent_support is not None and assisted_support is not None:
            raise ValueError("assisted labels must not overwrite independent labels")
        final_support = independent_support if independent_support is not None else assisted_support
        rows.append({
            "audit_number": case["audit_number"],
            "pilot_id": case["pilot_id"],
            "question_id": case["question_id"],
            "human_task_correct": task,
            "automatic_task_correct": automatic["task_correct"],
            "independent_human_evidence_supported": independent_support,
            "assisted_evidence_supported": assisted_support,
            "final_evidence_supported": final_support,
            "automatic_evidence_supported": automatic["evidence_supported"],
        })

    independent = [row for row in rows if row["independent_human_evidence_supported"] is not None]
    task_agreements = [row for row in rows if row["human_task_correct"] == row["automatic_task_correct"]]
    support_agreements = [
        row for row in independent
        if row["independent_human_evidence_supported"] == row["automatic_evidence_supported"]
    ]
    final_support_agreements = [
        row for row in rows
        if row["final_evidence_supported"] == row["automatic_evidence_supported"]
    ]
    exact_agreements = [
        row for row in rows
        if row["human_task_correct"] == row["automatic_task_correct"]
        and row["final_evidence_supported"] == row["automatic_evidence_supported"]
    ]

    def metric(numerator: int, denominator: int) -> dict[str, Any]:
        return {
            "agree": numerator,
            "total": denominator,
            "rate": numerator / denominator if denominator else None,
        }

    return {
        "schema_version": 1,
        "status": "complete",
        "split": worksheet.get("split"),
        "case_count": len(rows),
        "independent_human_review": {
            "task_label_coverage": metric(len(rows), len(rows)),
            "task_judge_agreement": metric(len(task_agreements), len(rows)),
            "support_label_coverage": metric(len(independent), len(rows)),
            "support_judge_agreement": metric(len(support_agreements), len(independent)),
            "support_uncertain_count": len(rows) - len(independent),
        },
        "after_user_accepted_assisted_adjudication": {
            "support_label_coverage": metric(len(rows), len(rows)),
            "support_judge_agreement": metric(len(final_support_agreements), len(rows)),
            "exact_pair_agreement": metric(len(exact_agreements), len(rows)),
        },
        "independent_support_disagreements": [
            row for row in independent
            if row["independent_human_evidence_supported"] != row["automatic_evidence_supported"]
        ],
        "assisted_audit_numbers": [
            row["audit_number"] for row in rows if row["assisted_evidence_supported"] is not None
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worksheet", required=True, type=Path)
    parser.add_argument("--automatic-audit", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable output: {args.output}")
    worksheet = json.loads(args.worksheet.read_text(encoding="utf-8"))
    automatic = json.loads(args.automatic_audit.read_text(encoding="utf-8"))
    report = build_agreement_report(worksheet, automatic)
    report["artifacts"] = {
        "worksheet_sha256": sha256_file(args.worksheet),
        "automatic_audit_sha256": sha256_file(args.automatic_audit),
    }
    write_json(args.output, report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
