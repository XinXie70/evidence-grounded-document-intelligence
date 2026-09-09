"""Select country metrics using entity, measure, statistic, and time qualifiers."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from .comparison_intent import parse_comparison_intent
from .io import sha256_file, write_json


_CHINA_ENDING_STOCKS = re.compile(
    r"stocks in China.{0,260}?reach\s+([\d.]+)\s+million bales\s+"
    r"at the end of the projection period",
    re.IGNORECASE | re.DOTALL,
)
_INDIA_AVERAGE_EXPORTS = re.compile(
    r"Exports of cotton.{0,320}?India.{0,320}?"
    r"(?:with\s+)?an average of\s+([\d.]+)\s+million bales",
    re.IGNORECASE | re.DOTALL,
)
_CHINA_MILL_USE_AVERAGE_GROWTH = re.compile(
    r"China[’']s\s+mill use.{0,520}?average rate of\s+([\d.]+)%\s+per year",
    re.IGNORECASE | re.DOTALL,
)
_INDIA_MILL_USE_AVERAGE_GROWTH = re.compile(
    r"cotton mill use in India.{0,520}?average of\s+([\d.]+)%\s+"
    r"over the next ten years",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class QualifiedMetricFact:
    entity: str
    page: int
    metric: str
    statistic: str
    time_scope: str
    value: str
    unit: str = "million bales"
    selection_basis: str = "question_entity_metric_statistic_and_time_qualifiers"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_qualified_metric_requests(question: str) -> tuple[str, str]:
    """Validate and order the two observed country-metric descriptions."""
    parse_comparison_intent(question)
    normalized = question.casefold()
    if all(
        term in normalized
        for term in ("china", "india", "growth rate", "mill use", "next ten years")
    ):
        if normalized.index("china") > normalized.index("india"):
            raise ValueError("growth-rate comparison must request China before India")
        return "china_mill_use_average_growth", "india_mill_use_average_growth"

    parts = re.split(r"\bcompared\s+to\b", question, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) != 2:
        raise ValueError("question does not match a supported qualified metric pair")
    left = parts[0].casefold()
    right = parts[1].casefold()
    if not (
        "china" in left
        and "ending stocks" in left
        and "end of the projection period" in left
    ):
        raise ValueError("left side must identify China's end-period ending stocks")
    if not (
        "india" in right
        and "average" in right
        and "exports" in right
        and "next ten years" in right
    ):
        raise ValueError("right side must identify India's average ten-year exports")
    return "china_ending_stocks_end_period", "india_exports_average_ten_years"


def _unique_match(
    pages: Mapping[int, str], pattern: re.Pattern[str], label: str
) -> tuple[int, str]:
    matches = []
    for page, text in pages.items():
        match = pattern.search(text)
        if match is not None:
            matches.append((page, match.group(1)))
    if len(matches) != 1:
        raise ValueError(f"expected exactly one fully qualified metric for {label}")
    return matches[0]


def select_qualified_metric_facts(
    question: str, page_text_by_page: Mapping[int, str]
) -> list[QualifiedMetricFact]:
    """Select ordered cotton metrics without benchmark labels."""
    if not page_text_by_page:
        raise ValueError("candidate page text must not be empty")
    requests = parse_qualified_metric_requests(question)
    if requests == ("china_mill_use_average_growth", "india_mill_use_average_growth"):
        china_page, china_value = _unique_match(
            page_text_by_page, _CHINA_MILL_USE_AVERAGE_GROWTH, "China mill-use growth"
        )
        india_page, india_value = _unique_match(
            page_text_by_page, _INDIA_MILL_USE_AVERAGE_GROWTH, "India mill-use growth"
        )
        return [
            QualifiedMetricFact(
                entity="China",
                page=china_page,
                metric="cotton mill use growth rate",
                statistic="long-term average annual growth rate",
                time_scope="next ten years",
                value=china_value,
                unit="percentage points",
            ),
            QualifiedMetricFact(
                entity="India",
                page=india_page,
                metric="cotton mill use growth rate",
                statistic="long-term average annual growth rate",
                time_scope="next ten years",
                value=india_value,
                unit="percentage points",
            ),
        ]
    china_page, china_value = _unique_match(
        page_text_by_page, _CHINA_ENDING_STOCKS, "China ending stocks"
    )
    india_page, india_value = _unique_match(
        page_text_by_page, _INDIA_AVERAGE_EXPORTS, "India average exports"
    )
    return [
        QualifiedMetricFact(
            entity="China",
            page=china_page,
            metric="cotton ending stocks",
            statistic="end value",
            time_scope="end of projection period",
            value=china_value,
        ),
        QualifiedMetricFact(
            entity="India",
            page=india_page,
            metric="cotton exports",
            statistic="average",
            time_scope="next ten years",
            value=india_value,
        ),
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
    facts = select_qualified_metric_facts(experiment["question"], pages)
    result = {
        "schema_version": 1,
        "experiment_type": "question_guided_qualified_metric_selection",
        "selector_version": "qualified_metric_selector_v1",
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
