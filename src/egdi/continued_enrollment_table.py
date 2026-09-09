"""Extract comparison facts from gender-specific enrolment tables continued across pages."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from .comparison_intent import parse_comparison_intent
from .io import sha256_file, write_json


_TARGET_PROGRAM = "Bachelor's and 1st Professional Degree"
_REPEATED_HEADER = re.compile(
    r"Program\s+Bachelor's and 1st Professional Degree\s+Master's Degree\s+"
    r"Doctoral Degree\s+Full-Time\s+Part-Time\s+Full-Time\s+Part-Time\s+"
    r"Full-Time\s+Part-Time",
    re.IGNORECASE,
)
_GRAND_TOTAL = re.compile(
    r"Grand Total\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+"
    r"([\d,]+)\s+([\d,]+)\s+([\d,]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ContinuedTableFact:
    group: str
    table_start_page: int
    total_page: int
    program: str
    status: str
    value: str
    unit: str = "students"
    selection_basis: str = (
        "question_group_and_column_with_repeated_header_page_continuation"
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_enrollment_request(question: str) -> tuple[tuple[str, str], str]:
    """Return ordered gender groups and requested attendance status."""
    parse_comparison_intent(question)
    normalized = question.casefold()
    professional_program = (
        "first professional" in normalized or "1st professional" in normalized
    )
    if "bachelor" not in normalized or not professional_program:
        raise ValueError("question is outside the supported enrolment comparison pattern")
    statuses = [status for status in ("full-time", "part-time") if status in normalized]
    if len(statuses) != 1:
        raise ValueError("question must identify exactly one enrolment status")
    positions = []
    for group in ("Female", "Male"):
        position = normalized.find(group.casefold())
        if position >= 0:
            positions.append((position, group))
    if len(positions) != 2:
        raise ValueError("question must compare distinct female and male groups")
    groups = tuple(group for _, group in sorted(positions))
    status = "Full-Time" if statuses[0] == "full-time" else "Part-Time"
    return (groups[0], groups[1]), status


def parse_enrollment_comparison(question: str) -> tuple[str, str]:
    """Backward-compatible group parser used by existing callers."""
    groups, _ = parse_enrollment_request(question)
    return groups


def _table_title(group: str) -> re.Pattern[str]:
    return re.compile(rf"\b{re.escape(group)} Enrolment by Program,\s*2008\b", re.IGNORECASE)


def _find_group_fact(
    group: str, status: str, pages: Mapping[int, str]
) -> ContinuedTableFact:
    start_candidates = [
        page
        for page, text in pages.items()
        if _table_title(group).search(text) and _REPEATED_HEADER.search(text)
    ]
    if len(start_candidates) != 1:
        raise ValueError(f"expected exactly one table start page for {group}")
    start_page = start_candidates[0]
    total_page = start_page + 1
    continuation = pages.get(total_page)
    if continuation is None:
        raise ValueError(f"candidate pages omit the continuation page for {group}")
    if _table_title(group).search(continuation):
        raise ValueError("continuation page unexpectedly starts a new gender table")
    if not _REPEATED_HEADER.search(continuation):
        raise ValueError(f"continuation page lacks the repeated table header for {group}")
    totals = _GRAND_TOTAL.search(continuation)
    if totals is None:
        raise ValueError(f"continuation page lacks a six-column Grand Total for {group}")
    # The repeated header fixes the first pair as Bachelor's Full-Time/Part-Time.
    value_group = 1 if status == "Full-Time" else 2
    value = totals.group(value_group).replace(",", "")
    return ContinuedTableFact(
        group=group,
        table_start_page=start_page,
        total_page=total_page,
        program=_TARGET_PROGRAM,
        status=status,
        value=value,
    )


def select_continued_enrollment_facts(
    question: str, page_text_by_page: Mapping[int, str]
) -> list[ContinuedTableFact]:
    """Select ordered female/male totals without benchmark labels."""
    if not page_text_by_page:
        raise ValueError("candidate page text must not be empty")
    groups, status = parse_enrollment_request(question)
    return [_find_group_fact(group, status, page_text_by_page) for group in groups]


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
    facts = select_continued_enrollment_facts(experiment["question"], pages)
    result = {
        "schema_version": 1,
        "experiment_type": "question_guided_continued_enrollment_table_selection",
        "selector_version": "continued_enrollment_table_v1",
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
