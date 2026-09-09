"""Question-guided fact selection from position-aware PDF table text."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from .io import sha256_file, write_json


_NUMBER = re.compile(r"^-?\d+(?:\.\d+)?$")
_TOKEN = re.compile(r"[a-z0-9]+")
_UNITS = {"hours", "minutes"}
_GENERIC = {
    "a", "according", "activity", "and", "average", "by", "distribution",
    "do", "does", "female", "females", "hour", "hours", "how", "main", "male",
    "males", "many", "minute", "minutes", "more", "of", "on", "per", "sex",
    "spend", "spent", "table", "than",
    "the", "time", "to", "total", "weekday",
}


@dataclass(frozen=True)
class PositionedWord:
    text: str
    x0: float
    x1: float
    top: float

    @property
    def center(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass(frozen=True)
class LayoutFact:
    page: int
    table_title: str
    unit: str
    row: str
    column_path: tuple[str, ...]
    value: str
    selection_basis: str

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["column_path"] = list(self.column_path)
        return result


def _tokens(text: str) -> set[str]:
    return {token.rstrip("s") if token in {"males", "females"} else token for token in _TOKEN.findall(text.casefold())}


def _activity_tokens(text: str) -> set[str]:
    return _tokens(text) - {_token.rstrip("s") if _token in {"males", "females"} else _token for _token in _GENERIC}


def group_words_into_lines(
    words: Sequence[PositionedWord], *, y_tolerance: float = 2.0
) -> list[list[PositionedWord]]:
    """Group words by vertical position and sort every line from left to right."""
    if y_tolerance < 0:
        raise ValueError("y_tolerance cannot be negative")
    lines: list[tuple[float, list[PositionedWord]]] = []
    for word in sorted(words, key=lambda item: (item.top, item.x0)):
        if not lines or abs(lines[-1][0] - word.top) > y_tolerance:
            lines.append((word.top, [word]))
        else:
            lines[-1][1].append(word)
    return [sorted(line, key=lambda item: item.x0) for _, line in lines]


def _line_text(line: Iterable[PositionedWord]) -> str:
    return " ".join(word.text for word in line)


def _group_ranges(headers: Sequence[PositionedWord]) -> dict[str, tuple[float, float, float]]:
    selected = [word for word in headers if word.text.casefold() in {"males", "females", "total"}]
    if len(selected) < 2:
        raise ValueError("table must expose at least two population headers")
    selected = sorted(selected, key=lambda word: word.center)
    ranges = {}
    for index, word in enumerate(selected):
        left = float("-inf") if index == 0 else (selected[index - 1].center + word.center) / 2
        right = float("inf") if index == len(selected) - 1 else (word.center + selected[index + 1].center) / 2
        ranges[word.text.casefold().rstrip("s")] = (left, right, word.center)
    return ranges


def extract_layout_facts(page: int, words: Sequence[PositionedWord]) -> list[LayoutFact]:
    """Extract numeric facts from the first hours/minutes table section on one page."""
    lines = group_words_into_lines(words)
    title_line = next((line for line in lines if line and line[0].text.casefold() == "table"), None)
    if title_line is None:
        raise ValueError("page does not contain a table title")
    title = _line_text(title_line)
    unit_index = next(
        (index for index, line in enumerate(lines) if _line_text(line).strip().casefold() in _UNITS),
        None,
    )
    if unit_index is None:
        raise ValueError("page does not contain an hours or minutes table section")
    unit = _line_text(lines[unit_index]).strip().casefold()
    end_index = next(
        (
            index
            for index in range(unit_index + 1, len(lines))
            if _line_text(lines[index]).strip().casefold() in {"percentage", "percent"}
        ),
        len(lines),
    )
    section = lines[unit_index + 1 : end_index]
    header_line = next(
        (
            line
            for line in section
            if {word.text.casefold() for word in line} & {"males", "females"}
        ),
        None,
    )
    if header_line is None:
        raise ValueError("table section does not contain population headers")
    ranges = _group_ranges(header_line)

    first_data_index = next(
        (index for index, line in enumerate(section) if sum(bool(_NUMBER.fullmatch(word.text)) for word in line) >= len(ranges)),
        None,
    )
    if first_data_index is None:
        raise ValueError("table section does not contain numeric rows")
    subheader_words = [
        word
        for line in section[:first_data_index]
        for word in line
        if word.text.casefold() in {"married", "single", "total"}
    ]

    facts: list[LayoutFact] = []
    for line in section[first_data_index:]:
        numeric = [word for word in line if _NUMBER.fullmatch(word.text)]
        if len(numeric) < len(ranges):
            continue
        first_numeric_x = min(word.x0 for word in numeric)
        row = _line_text(word for word in line if word.x1 < first_numeric_x).strip()
        if not row:
            continue
        for group, (left, right, center) in ranges.items():
            values = [word for word in numeric if left <= word.center < right]
            if not values:
                continue
            group_subheaders = [word for word in subheader_words if left <= word.center < right]
            total_header = next(
                (word for word in group_subheaders if word.text.casefold() == "total"),
                None,
            )
            target_x = total_header.center if total_header is not None else center
            value = min(values, key=lambda word: abs(word.center - target_x))
            path = (group.title(), "Total") if total_header is not None else (group.title(),)
            facts.append(
                LayoutFact(
                    page=page,
                    table_title=title,
                    unit=unit,
                    row=row,
                    column_path=path,
                    value=value.text,
                    selection_basis="position_aware_table_extraction",
                )
            )
    return facts


def _group_for_clause(clause: str) -> str | None:
    tokens = _tokens(clause)
    if "male" in tokens and "female" not in tokens:
        return "Male"
    if "female" in tokens and "male" not in tokens:
        return "Female"
    return None


def _resolution_hours(fact: LayoutFact) -> float:
    decimal_places = len(fact.value.partition(".")[2])
    resolution = 10 ** (-decimal_places)
    return resolution / 60 if fact.unit == "minutes" else resolution


def _value_hours(fact: LayoutFact) -> float:
    value = float(fact.value)
    return value / 60 if fact.unit == "minutes" else value


def select_comparison_facts(question: str, facts: Sequence[LayoutFact]) -> list[LayoutFact]:
    """Select one precise fact for each side of an explicit 'more ... than ...' question."""
    clauses = re.split(r"\bthan\b", question, maxsplit=1, flags=re.IGNORECASE)
    if len(clauses) != 2:
        raise ValueError("question must contain one explicit 'than' comparison")
    selected: list[LayoutFact] = []
    for clause in clauses:
        group = _group_for_clause(clause)
        activity = _activity_tokens(clause)
        if group is None or not activity:
            raise ValueError("each comparison clause must identify a population and activity")
        candidates = []
        for fact in facts:
            if fact.column_path[0] != group:
                continue
            row_tokens = _activity_tokens(fact.row)
            title_tokens = _activity_tokens(fact.table_title)
            if activity <= row_tokens:
                candidates.append((fact, "row_match"))
            elif fact.row.casefold() == "total" and activity <= title_tokens:
                candidates.append((fact, "table_scope_total"))
        if not candidates:
            raise ValueError(f"no table fact matches comparison clause: {clause.strip()}")

        # Prefer a finer-grained consistent measurement over a rounded summary.
        best_fact, best_basis = min(candidates, key=lambda item: _resolution_hours(item[0]))
        consistent = [
            item
            for item in candidates
            if abs(_value_hours(item[0]) - _value_hours(best_fact)) <= 0.051
        ]
        if len(consistent) == len(candidates):
            best_fact, best_basis = min(consistent, key=lambda item: _resolution_hours(item[0]))
        else:
            best_fact, best_basis = next(
                (item for item in candidates if item[1] == "row_match"),
                candidates[0],
            )
        selected.append(
            LayoutFact(
                page=best_fact.page,
                table_title=best_fact.table_title,
                unit=best_fact.unit,
                row=best_fact.row,
                column_path=best_fact.column_path,
                value=best_fact.value,
                selection_basis=f"{best_basis}; finest_consistent_resolution",
            )
        )
    return selected


def load_pdf_words(pdf_path: Path, pages: Sequence[int]) -> dict[int, list[PositionedWord]]:
    """Load word coordinates lazily so pure selection tests need no PDF dependency."""
    try:
        import pdfplumber
    except ImportError as error:  # pragma: no cover - environment-specific
        raise RuntimeError("pdfplumber is required for layout-aware table extraction") from error
    output = {}
    with pdfplumber.open(pdf_path) as document:
        for page in pages:
            raw_words = document.pages[page - 1].extract_words(x_tolerance=2, y_tolerance=3)
            output[page] = [
                PositionedWord(
                    text=item["text"],
                    x0=float(item["x0"]),
                    x1=float(item["x1"]),
                    top=float(item["top"]),
                )
                for item in raw_words
            ]
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    source = json.loads(args.input.read_text(encoding="utf-8"))
    pages = source["evidence_pages"]
    question = source["model_input"]["question"]
    words_by_page = load_pdf_words(args.pdf, pages)
    candidates = [
        fact
        for page in pages
        for fact in extract_layout_facts(page, words_by_page[page])
    ]
    selected = select_comparison_facts(question, candidates)
    result = {
        "schema_version": 1,
        "experiment_type": "oracle_page_question_guided_layout_fact_selection",
        "question_id": source["question_id"],
        "doc_id": source["doc_id"],
        "question": question,
        "evidence_pages": pages,
        "selected_facts": [fact.to_dict() for fact in selected],
        "candidate_fact_count": len(candidates),
        "uses_gold_pages_to_isolate_fact_selection": True,
        "uses_gold_answer_or_gold_facts": False,
        "paid_api_used": False,
        "source_input_sha256": sha256_file(args.input),
        "source_pdf_sha256": sha256_file(args.pdf),
    }
    write_json(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
