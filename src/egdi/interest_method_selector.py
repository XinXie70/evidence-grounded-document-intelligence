"""Select total-interest facts from compared simple and compound method examples."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from .io import sha256_file, write_json


_TOTAL_INTEREST = re.compile(r"\bTotal\s+Interest\s+([\d,]+(?:\.\d+)?)\b", re.IGNORECASE)
_DOLLAR_AMOUNT = re.compile(r"\$\s*[\d,]+(?:\.\d+)?")


@dataclass(frozen=True)
class InterestMethodFact:
    method: str
    page: int
    row: str
    value: str
    unit: str = "dollars"
    selection_basis: str = "question_method_to_definition_scoped_total_interest"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_interest_methods(question: str) -> tuple[str, str]:
    """Return ordered interest methods from a directional compared-to question."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a non-empty string")
    parts = re.split(r"\bcompared\s+to\b", question, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) != 2:
        raise ValueError("question must contain one explicit 'compared to' comparison")

    def method(part: str) -> str | None:
        normalized = part.casefold()
        has_compound = "compound interest" in normalized
        has_simple = "simple interest" in normalized
        if has_compound == has_simple:
            return None
        return "Compound Interest" if has_compound else "Simple Interest"

    methods = tuple(method(part) for part in parts)
    if None in methods or methods[0] == methods[1]:
        raise ValueError("question must compare distinct simple and compound interest methods")
    return methods  # type: ignore[return-value]


def _definition_pattern(method: str) -> re.Pattern[str]:
    return re.compile(
        rf"\b{re.escape(method)}\b.{0,160}?\bInterest\s+is\s+charged\b",
        re.IGNORECASE | re.DOTALL,
    )


def _find_method_fact(method: str, pages: Mapping[int, str]) -> InterestMethodFact:
    candidates = []
    definition = _definition_pattern(method)
    for page, text in pages.items():
        heading = definition.search(text)
        totals = _TOTAL_INTEREST.findall(text)
        if heading is None or len(totals) != 1:
            continue
        if _DOLLAR_AMOUNT.search(text) is None:
            continue
        candidates.append((page, totals[0].replace(",", "")))
    if len(candidates) != 1:
        raise ValueError(f"expected exactly one definition-scoped Total Interest for {method}")
    page, value = candidates[0]
    return InterestMethodFact(method=method, page=page, row="Total Interest", value=value)


def select_interest_method_facts(
    question: str, page_text_by_page: Mapping[int, str]
) -> list[InterestMethodFact]:
    """Select ordered total-interest facts without benchmark labels."""
    if not page_text_by_page:
        raise ValueError("candidate page text must not be empty")
    return [
        _find_method_fact(method, page_text_by_page)
        for method in parse_interest_methods(question)
    ]


def _load_candidate_pages(path: Path, candidates: Sequence[int]) -> dict[int, str]:
    wanted = set(candidates)
    output: dict[int, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        page = record.get("page")
        if page in wanted:
            output[page] = record.get("text", "")
    missing = wanted - output.keys()
    if missing:
        raise ValueError(f"candidate pages missing from page records: {sorted(missing)}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--page-records", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable selection: {args.output}")
    experiment = json.loads(args.input.read_text(encoding="utf-8"))
    pages = _load_candidate_pages(args.page_records, experiment["candidate_pages"])
    facts = select_interest_method_facts(experiment["question"], pages)
    result = {
        "schema_version": 1,
        "experiment_type": "question_guided_interest_method_selection",
        "selector_version": "interest_method_selector_v0",
        "question_id": experiment["question_id"],
        "doc_id": experiment["doc_id"],
        "question": experiment["question"],
        "candidate_page_count": len(pages),
        "selected_facts": [fact.to_dict() for fact in facts],
        "uses_gold_answer": False,
        "uses_gold_evidence_pages": False,
        "input_sha256": sha256_file(args.input),
        "page_records_sha256": sha256_file(args.page_records),
        "paid_api_used": False,
    }
    write_json(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
