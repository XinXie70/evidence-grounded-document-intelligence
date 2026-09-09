"""Post-hoc score a completed comparison probe against DocScope labels."""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import json
import re
from pathlib import Path
from typing import Any

from .io import sha256_file, write_json


_NUMBER = re.compile(r"[-+]?\d+(?:\.\d+)?")


def _gold_number(answer: str) -> Decimal:
    matches = _NUMBER.findall(answer.replace(",", ""))
    if len(matches) == 2:
        try:
            return abs(Decimal(matches[0]) - Decimal(matches[1]))
        except InvalidOperation as error:
            raise ValueError("gold answer operands are not numeric") from error
    if len(matches) != 1:
        result_cue = re.search(
            r"\bdifference\s+(?:is\s+)?(?:calculated\s+as\s+)?"
            r"([-+]?\d+(?:\.\d+)?)",
            answer.replace(",", ""),
            flags=re.IGNORECASE,
        )
        if result_cue is None:
            raise ValueError(
                "multi-number gold answer must explicitly identify the difference"
            )
        matches = [result_cue.group(1)]
    try:
        return Decimal(matches[0])
    except InvalidOperation as error:
        raise ValueError("gold answer is not numeric") from error


def _predicted_pages(facts: list[dict[str, Any]]) -> list[int]:
    pages = []
    for fact in facts:
        candidates = fact.get("cited_pages")
        if candidates is None:
            candidates = [fact.get("total_page", fact.get("page"))]
        if not isinstance(candidates, list) or not candidates:
            raise ValueError("selected fact must expose value-page provenance")
        for page in candidates:
            if not isinstance(page, int) or isinstance(page, bool) or page < 1:
                raise ValueError("selected fact must expose positive value pages")
            if page not in pages:
                pages.append(page)
    return pages


def score_probe(probe: dict[str, Any], benchmark: list[dict[str, Any]]) -> dict[str, Any]:
    leakage = probe.get("leakage_controls", {})
    if leakage.get("uses_gold_answer") is not False:
        raise ValueError("probe is not label-free")
    if leakage.get("uses_gold_evidence_pages") is not False:
        raise ValueError("probe is not evidence-label-free")
    labels = {item.get("id"): item for item in benchmark}
    scored = []
    for case in probe.get("cases", []):
        label = labels.get(case.get("question_id"))
        if label is None or label.get("split") != "dev":
            raise ValueError("probe question must match a DocScope dev label")
        if label.get("question") != case.get("question"):
            raise ValueError("probe question text drifted from benchmark")
        if case.get("status") != "success":
            scored.append(
                {"case_id": case["case_id"], "status": "unsupported", "answer_match": False,
                 "complete_evidence_match": False}
            )
            continue
        predicted = Decimal(case["deterministic_comparison"]["magnitude"])
        gold = _gold_number(label["answer"]["answer_text"])
        predicted_pages = sorted(_predicted_pages(case["selected_facts"]))
        gold_pages = sorted({evidence["page"] for evidence in label["evidences"]})
        scored.append(
            {
                "case_id": case["case_id"],
                "status": "scored",
                "predicted_magnitude": format(predicted, "f"),
                "gold_magnitude": format(gold, "f"),
                "answer_match": predicted == gold,
                "predicted_value_pages": predicted_pages,
                "gold_evidence_pages": gold_pages,
                "complete_evidence_match": predicted_pages == gold_pages,
            }
        )
    count = len(scored)
    if count == 0:
        raise ValueError("probe has no cases to score")
    answer_correct = sum(item["answer_match"] for item in scored)
    evidence_correct = sum(item["complete_evidence_match"] for item in scored)
    return {
        "schema_version": 1,
        "experiment_type": "posthoc_comparison_generalization_score",
        "split": "development_tune",
        "cases": scored,
        "summary": {
            "case_count": count,
            "answer_exact_match_count": answer_correct,
            "answer_exact_match_rate": answer_correct / count,
            "complete_evidence_match_count": evidence_correct,
            "complete_evidence_match_rate": evidence_correct / count,
        },
        "gold_labels_used_only_after_predictions_frozen": True,
        "paid_api_used": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable score: {args.output}")
    probe = json.loads(args.probe.read_text(encoding="utf-8"))
    benchmark = json.loads(args.benchmark.read_text(encoding="utf-8"))
    result = score_probe(probe, benchmark)
    result["probe_sha256"] = sha256_file(args.probe)
    result["benchmark_sha256"] = sha256_file(args.benchmark)
    write_json(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
