"""Normalize heterogeneous evidence selectors into one comparison contract.

The adapters in this module are keyed by selector *type*, never by question id.
They preserve source-specific semantics in ``qualifiers`` while exposing the
same two operands to downstream arithmetic and reliability checks.
"""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from typing import Any, Callable

from .comparison_intent import parse_comparison_intent
from .io import sha256_file, write_json


def _nonempty_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _decimal_text(value: Any) -> str:
    text = _nonempty_text(value, "fact.value")
    try:
        number = Decimal(text)
    except InvalidOperation as error:
        raise ValueError("fact.value must be a decimal string") from error
    if not number.is_finite():
        raise ValueError("fact.value must be finite")
    return text


def _pages(*values: Any) -> list[int]:
    pages: list[int] = []
    for value in values:
        items = value if isinstance(value, list) else [value]
        for item in items:
            if not isinstance(item, int) or isinstance(item, bool) or item < 1:
                raise ValueError("provenance pages must be positive integers")
            if item not in pages:
                pages.append(item)
    if not pages:
        raise ValueError("each operand must have at least one provenance page")
    return pages


def _clean_qualifiers(**values: Any) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value not in (None, "", [])}


def _operand(
    fact: dict[str, Any],
    *,
    label: str,
    metric: str,
    source_type: str,
    value_pages: list[int],
    supporting_pages: list[int],
    qualifiers: dict[str, Any],
) -> dict[str, Any]:
    if not set(value_pages).issubset(supporting_pages):
        raise ValueError("supporting_pages must include all value_pages")
    return {
        "label": _nonempty_text(label, "operand.label"),
        "metric": _nonempty_text(metric, "operand.metric"),
        "value": _decimal_text(fact.get("value")),
        "unit": _nonempty_text(fact.get("unit"), "fact.unit"),
        "qualifiers": qualifiers,
        "provenance": {
            "source_type": source_type,
            "value_pages": value_pages,
            "supporting_pages": supporting_pages,
            "selection_basis": _nonempty_text(
                fact.get("selection_basis"), "fact.selection_basis"
            ),
        },
    }


def _layout(fact: dict[str, Any]) -> dict[str, Any]:
    page = _pages(fact.get("page"))
    path = fact.get("column_path")
    if not isinstance(path, list) or not path:
        raise ValueError("layout fact column_path must be a non-empty list")
    label = " / ".join(_nonempty_text(item, "column_path item") for item in path)
    return _operand(
        fact,
        label=label,
        metric=fact.get("row") or fact.get("table_title"),
        source_type="layout_table",
        value_pages=page,
        supporting_pages=page,
        qualifiers=_clean_qualifiers(
            table_title=fact.get("table_title"), column_path=path, row=fact.get("row")
        ),
    )


def _list_count(fact: dict[str, Any]) -> dict[str, Any]:
    pages = _pages(fact.get("pages"))
    return _operand(
        fact,
        label=fact.get("topic"),
        metric="numbered list count",
        source_type="numbered_list",
        value_pages=pages,
        supporting_pages=pages,
        qualifiers=_clean_qualifiers(
            marker_style=fact.get("marker_style"),
            observed_numbers=fact.get("observed_numbers"),
        ),
    )


def _continued_enrollment(fact: dict[str, Any]) -> dict[str, Any]:
    value_pages = _pages(fact.get("total_page"))
    supporting = _pages(fact.get("table_start_page"), fact.get("total_page"))
    return _operand(
        fact,
        label=fact.get("group"),
        metric=f"{fact.get('status', '')} {fact.get('program', '')} enrollment".strip(),
        source_type="continued_table",
        value_pages=value_pages,
        supporting_pages=supporting,
        qualifiers=_clean_qualifiers(
            program=fact.get("program"), status=fact.get("status")
        ),
    )


def _product_dimension(fact: dict[str, Any]) -> dict[str, Any]:
    value_pages = _pages(fact.get("value_page"))
    supporting = _pages(
        fact.get("identity_page"), fact.get("dimension_anchor_page"), fact.get("value_page")
    )
    return _operand(
        fact,
        label=fact.get("product_id"),
        metric=fact.get("dimension"),
        source_type="product_specification",
        value_pages=value_pages,
        supporting_pages=supporting,
        qualifiers=_clean_qualifiers(descriptor=fact.get("descriptor")),
    )


def _interest_method(fact: dict[str, Any]) -> dict[str, Any]:
    pages = _pages(fact.get("page"))
    return _operand(
        fact,
        label=fact.get("method"),
        metric=fact.get("row"),
        source_type="worked_example",
        value_pages=pages,
        supporting_pages=pages,
        qualifiers={},
    )


def _balance_sheet(fact: dict[str, Any]) -> dict[str, Any]:
    pages = _pages(fact.get("page"))
    return _operand(
        fact,
        label=fact.get("entity"),
        metric=fact.get("row"),
        source_type="balance_sheet",
        value_pages=pages,
        supporting_pages=pages,
        qualifiers=_clean_qualifiers(
            as_of_date=fact.get("as_of_date"), discriminator=fact.get("discriminator")
        ),
    )


def _qualified_metric(fact: dict[str, Any]) -> dict[str, Any]:
    pages = _pages(fact.get("page"))
    return _operand(
        fact,
        label=fact.get("entity"),
        metric=fact.get("metric"),
        source_type="qualified_metric",
        value_pages=pages,
        supporting_pages=pages,
        qualifiers=_clean_qualifiers(
            statistic=fact.get("statistic"), time_scope=fact.get("time_scope")
        ),
    )


_ADAPTERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "oracle_page_question_guided_layout_fact_selection": _layout,
    "list_count_selector_v1_excludes_reference_sections": _list_count,
    "continued_enrollment_table_v0": _continued_enrollment,
    "continued_enrollment_table_v1": _continued_enrollment,
    "product_dimension_selector_v0": _product_dimension,
    "interest_method_selector_v0": _interest_method,
    "balance_sheet_selector_v0": _balance_sheet,
    "qualified_metric_selector_v0": _qualified_metric,
    "qualified_metric_selector_v1": _qualified_metric,
}


def adapt_selection(selection: dict[str, Any]) -> dict[str, Any]:
    """Convert one selector result into the stable comparison contract."""
    uses_gold_answer = selection.get(
        "uses_gold_answer", selection.get("uses_gold_answer_or_gold_facts")
    )
    uses_gold_pages = selection.get(
        "uses_gold_evidence_pages", selection.get("uses_gold_pages_to_isolate_fact_selection")
    )
    if not isinstance(uses_gold_answer, bool):
        raise ValueError("selection must explicitly declare whether gold answers were used")
    if not isinstance(uses_gold_pages, bool):
        raise ValueError("selection must explicitly declare whether gold evidence pages were used")
    facts = selection.get("selected_facts")
    if not isinstance(facts, list) or len(facts) != 2:
        raise ValueError("comparison contract requires exactly two ordered selected_facts")
    adapter_id = selection.get("selector_version") or selection.get("experiment_type")
    adapter = _ADAPTERS.get(adapter_id)
    if adapter is None:
        raise ValueError(f"unsupported selector type: {adapter_id!r}")
    operands = [adapter(fact) for fact in facts]
    return {
        "schema_version": 1,
        "contract_type": "comparison_evidence",
        "question_id": _nonempty_text(selection.get("question_id"), "question_id"),
        "doc_id": _nonempty_text(selection.get("doc_id"), "doc_id"),
        "question": _nonempty_text(selection.get("question"), "question"),
        "operation": parse_comparison_intent(selection["question"]).operation,
        "left": operands[0],
        "right": operands[1],
        "source_selector_type": adapter_id,
        "leakage_controls": {
            "uses_gold_answer_or_facts": uses_gold_answer,
            "uses_gold_evidence_pages": uses_gold_pages,
        },
        "evaluation_eligibility": {
            "grounded_reasoning": "ineligible_gold_answer_or_facts"
            if uses_gold_answer
            else "eligible",
            "evidence_retrieval": "ineligible_gold_evidence_pages"
            if uses_gold_pages
            else "eligible",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite immutable contract: {args.output}")
    selection = json.loads(args.input.read_text(encoding="utf-8"))
    contract = adapt_selection(selection)
    contract["source_selection_sha256"] = sha256_file(args.input)
    contract["paid_api_used"] = False
    write_json(args.output, contract)
    print(json.dumps(contract, indent=2))


if __name__ == "__main__":
    main()
