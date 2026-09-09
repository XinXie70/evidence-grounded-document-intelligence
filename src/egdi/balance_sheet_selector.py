"""Select entity-scoped Total Assets from compared balance sheets."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from .io import sha256_file, write_json


_BALANCE_TITLE = re.compile(r"([A-Za-z][A-Za-z ]{1,50}):\s*Balance Sheet", re.IGNORECASE)
_TOTAL_ASSETS = re.compile(r"\bTOTAL ASSETS\s+([\d,]+(?:\.\d+)?)\b", re.IGNORECASE)
_BILLION_YEN = re.compile(r"\bBillion Yen\b", re.IGNORECASE)
_DATE = re.compile(r"\bJun(?:e)?\s+30,\s*2007\b", re.IGNORECASE)
_INSTALLMENT_ROW = re.compile(r"\bInstallment accounts receivable\s+[\d,.]+", re.IGNORECASE)
_LOAN_ROW = re.compile(
    r"\bCURRENT ASSETS\b.{0,350}?"
    r"(?<!securitized )(?<!installment accounts )\bLoan receivables\s+[\d,.]+",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class BalanceSheetFact:
    entity: str
    page: int
    discriminator: str
    as_of_date: str
    row: str
    value: str
    unit: str = "billion yen"
    selection_basis: str = "question_discriminator_to_dated_balance_sheet_total_assets"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_balance_sheet_discriminators(question: str) -> tuple[str, str]:
    """Return ordered asset-row signals from a compared-to balance-sheet question."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a non-empty string")
    parts = re.split(r"\bcompared\s+to\b", question, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) != 2:
        raise ValueError("question must contain one explicit 'compared to' comparison")

    def discriminator(part: str) -> str | None:
        normalized = part.casefold()
        if "installment accounts receivable" in normalized:
            return "installment_accounts_receivable"
        if "loan receivables" in normalized:
            return "loan_receivables_current_asset_row"
        return None

    signals = tuple(discriminator(part) for part in parts)
    if None in signals or signals[0] == signals[1]:
        raise ValueError("question must provide two distinct balance-sheet asset signals")
    return signals  # type: ignore[return-value]


def _matches_discriminator(text: str, discriminator: str) -> bool:
    if discriminator == "installment_accounts_receivable":
        return bool(_INSTALLMENT_ROW.search(text))
    if discriminator == "loan_receivables_current_asset_row":
        return bool(_LOAN_ROW.search(text))
    raise ValueError(f"unsupported discriminator: {discriminator}")


def _find_balance_sheet_fact(
    discriminator: str, pages: Mapping[int, str]
) -> BalanceSheetFact:
    candidates = []
    for page, text in pages.items():
        title = _BALANCE_TITLE.search(text)
        totals = _TOTAL_ASSETS.findall(text)
        if (
            title is None
            or len(totals) != 1
            or _BILLION_YEN.search(text) is None
            or _DATE.search(text) is None
            or not _matches_discriminator(text, discriminator)
        ):
            continue
        candidates.append((page, title.group(1).strip(), totals[0].replace(",", "")))
    if len(candidates) != 1:
        raise ValueError(f"expected exactly one dated balance sheet for {discriminator}")
    page, entity, value = candidates[0]
    return BalanceSheetFact(
        entity=entity,
        page=page,
        discriminator=discriminator,
        as_of_date="2007-06-30",
        row="Total Assets",
        value=value,
    )


def select_balance_sheet_facts(
    question: str, page_text_by_page: Mapping[int, str]
) -> list[BalanceSheetFact]:
    """Select ordered Total Assets facts without benchmark labels."""
    if not page_text_by_page:
        raise ValueError("candidate page text must not be empty")
    return [
        _find_balance_sheet_fact(discriminator, page_text_by_page)
        for discriminator in parse_balance_sheet_discriminators(question)
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
    facts = select_balance_sheet_facts(experiment["question"], pages)
    result = {
        "schema_version": 1,
        "experiment_type": "question_guided_balance_sheet_selection",
        "selector_version": "balance_sheet_selector_v0",
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
