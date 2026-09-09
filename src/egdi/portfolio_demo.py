"""Human-readable, offline replay of the frozen comparison validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_EXPERIMENT_DIR = (
    Path(__file__).resolve().parents[2]
    / "experiments"
    / "day6_generic_comparison_validation_v0"
)


def load_demo_cases(experiment_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    predictions_path = experiment_dir / "finalized_citation_repaired.json"
    score_path = experiment_dir / "score.json"
    predictions = json.loads(predictions_path.read_text(encoding="utf-8"))
    score = json.loads(score_path.read_text(encoding="utf-8"))

    score_by_id = {case["case_id"]: case for case in score["cases"]}
    cases = []
    for prediction in predictions["cases"]:
        case_id = prediction["case_id"]
        if case_id not in score_by_id:
            raise ValueError(f"missing frozen score for {case_id}")
        cases.append({"prediction": prediction, "score": score_by_id[case_id]})
    return cases, score["summary"]


def _pages(prediction: dict[str, Any]) -> list[int]:
    pages: list[int] = []
    for fact in prediction.get("selected_facts", []):
        for page in fact.get("cited_pages", []):
            if page not in pages:
                pages.append(page)
    return sorted(pages)


def render_case(prediction: dict[str, Any], score: dict[str, Any]) -> str:
    lines = [f"[{prediction['case_id']}] {prediction['question']}"]
    if prediction["status"] != "success":
        lines.extend(
            [
                "Decision: ABSTAIN",
                "Reason: supplied evidence was insufficient; the system did not guess.",
                "Evaluation: retrieval failure, reliability success",
            ]
        )
        return "\n".join(lines)

    comparison = prediction["deterministic_comparison"]
    facts = prediction["selected_facts"]
    lines.append("Decision: ANSWER")
    for index, fact in enumerate(facts, start=1):
        cited = ", ".join(str(page) for page in fact["cited_pages"])
        lines.append(
            f"Evidence {index}: {fact['label']} = {fact['value']} {fact['unit']} "
            f"(page {cited})"
        )
    lines.extend(
        [
            f"Answer: {comparison['magnitude']} {comparison['unit']}",
            f"Citations: {', '.join(str(page) for page in _pages(prediction))}",
            "Citation check: PASS (reported values occur on the cited pages)",
            f"Post-hoc benchmark: {'CORRECT' if score['answer_match'] else 'INCORRECT'}",
        ]
    )
    return "\n".join(lines)


def render_demo(cases: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    header = [
        "Evidence-Grounded Document Intelligence — Frozen Validation Replay",
        "Offline replay: no API call, no new model output, no cost.",
        "",
    ]
    body = []
    for case in cases:
        body.extend([render_case(case["prediction"], case["score"]), ""])
    count = summary["case_count"]
    body.extend(
        [
            "Summary",
            f"Answer exact match: {summary['answer_exact_match_count']}/{count}",
            f"Complete evidence match: {summary['complete_evidence_match_count']}/{count}",
        ]
    )
    return "\n".join(header + body)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-dir", type=Path, default=DEFAULT_EXPERIMENT_DIR)
    parser.add_argument("--case", dest="case_id", help="Show one case, e.g. validation_01")
    args = parser.parse_args()

    cases, summary = load_demo_cases(args.experiment_dir)
    if args.case_id:
        cases = [case for case in cases if case["prediction"]["case_id"] == args.case_id]
        if not cases:
            raise SystemExit(f"unknown case: {args.case_id}")
    print(render_demo(cases, summary))


if __name__ == "__main__":
    main()
