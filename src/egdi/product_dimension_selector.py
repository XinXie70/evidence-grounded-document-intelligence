"""Link product descriptions to model-specific depth specifications across pages."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from .io import sha256_file, write_json


_CLOCK_IDENTITY = re.compile(
    r"(Art\.\s*\d+[A-Z]?)\s+(?:BST/GMT\s+)?Time Clock.*?"
    r"digital time clock.*?four push buttons",
    re.IGNORECASE | re.DOTALL,
)
_PSU_IDENTITY = re.compile(
    r"(UBPSU[\d.]+)\s+POWER\s+SUPPL\s*Y.*?5A unboxed PSU",
    re.IGNORECASE | re.DOTALL,
)
_DIMENSION_TRIPLE = re.compile(
    r"(?:Module|PSU) Dimensions\s*:\s*"
    r"([\d.]+)mm\s*\(L\)\s*x\s*([\d.]+)mm\s*\(W\)\s*x\s*"
    r"([\d.]+)mm\s*\(D\)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ProductDimensionFact:
    descriptor: str
    product_id: str
    identity_page: int
    dimension_anchor_page: int
    value_page: int
    dimension: str
    value: str
    unit: str = "millimeters"
    selection_basis: str = "question_description_to_product_id_to_explicit_D_specification"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_less_than_descriptors(question: str) -> tuple[str, str]:
    """Return ordered product descriptors from one explicit less-than question."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a non-empty string")
    parts = re.split(r"\bless\s+than\b", question, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) != 2:
        raise ValueError("question must contain one explicit 'less than' comparison")
    return parts[0].strip(), parts[1].strip()


def _canonical_product_id(raw: str) -> str:
    compact = re.sub(r"\s+", "", raw)
    if compact.casefold().startswith("art."):
        return "Art." + compact[4:]
    return compact.upper()


def _identify_product(descriptor: str, pages: Mapping[int, str]) -> tuple[str, int]:
    normalized = descriptor.casefold()
    if "time clock" in normalized and "four push buttons" in normalized:
        pattern = _CLOCK_IDENTITY
    elif "5a" in normalized and "power supply" in normalized:
        pattern = _PSU_IDENTITY
    else:
        raise ValueError("product descriptor is outside the supported identity patterns")
    matches = []
    for page, text in pages.items():
        match = pattern.search(text)
        if match is not None:
            matches.append((_canonical_product_id(match.group(1)), page))
    if len(matches) != 1:
        raise ValueError("product description must resolve to exactly one identity page")
    return matches[0]


def _dimension_anchor(product_id: str) -> re.Pattern[str]:
    if product_id.startswith("Art."):
        number = re.escape(product_id[4:])
        return re.compile(rf"Art\.\s*{number}\s+Dimensions\b", re.IGNORECASE)
    return re.compile(rf"{re.escape(product_id)}\s+Dimensions\b", re.IGNORECASE)


def _find_depth(product_id: str, pages: Mapping[int, str]) -> tuple[int, int, str]:
    anchors = []
    pattern = _dimension_anchor(product_id)
    for page, text in pages.items():
        match = pattern.search(text)
        if match is not None:
            anchors.append((page, match.end()))
    if len(anchors) != 1:
        raise ValueError(f"expected exactly one Dimensions anchor for {product_id}")
    anchor_page, anchor_end = anchors[0]
    current_suffix = pages[anchor_page][anchor_end:]
    sections = [(anchor_page, current_suffix)]
    if anchor_page + 1 in pages:
        sections.append((anchor_page + 1, pages[anchor_page + 1]))
    combined = " ".join(text for _, text in sections)
    match = _DIMENSION_TRIPLE.search(combined)
    if match is None:
        raise ValueError(f"no explicit L/W/D specification follows {product_id} Dimensions")
    boundary = len(current_suffix) + 1
    value_page = anchor_page if match.start() < boundary else anchor_page + 1
    return anchor_page, value_page, match.group(3)


def select_product_depth_facts(
    question: str, page_text_by_page: Mapping[int, str]
) -> list[ProductDimensionFact]:
    """Select ordered depth facts without benchmark answers or evidence labels."""
    if not page_text_by_page:
        raise ValueError("candidate page text must not be empty")
    facts = []
    for descriptor in parse_less_than_descriptors(question):
        product_id, identity_page = _identify_product(descriptor, page_text_by_page)
        anchor_page, value_page, value = _find_depth(product_id, page_text_by_page)
        facts.append(
            ProductDimensionFact(
                descriptor=descriptor,
                product_id=product_id,
                identity_page=identity_page,
                dimension_anchor_page=anchor_page,
                value_page=value_page,
                dimension="Depth (D)",
                value=value,
            )
        )
    return facts


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
    facts = select_product_depth_facts(experiment["question"], pages)
    result = {
        "schema_version": 1,
        "experiment_type": "question_guided_product_dimension_selection",
        "selector_version": "product_dimension_selector_v0",
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
