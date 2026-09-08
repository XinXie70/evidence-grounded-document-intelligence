"""Build deterministic, answer-free inputs for grounded-reasoning experiments."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .access import load_records
from .corpus import read_page_records_jsonl
from .io import write_json
from .text import PageRecord


REAL_RETRIEVAL = "real_retrieval"
ORACLE_PAGE = "oracle_page"
CLOSED_BOOK = "closed_book"
SUPPORTED_CONDITIONS = (CLOSED_BOOK, REAL_RETRIEVAL, ORACLE_PAGE)

DRAFT_INSTRUCTIONS = (
    "Answer the question using only the supplied document evidence. "
    "If the evidence does not adequately support an answer, return "
    "status='insufficient_evidence' and answer=null. Cite only supplied "
    "1-based physical PDF page numbers. Return one object matching response_schema."
)

PILOT_INSTRUCTIONS_V1 = (
    "Answer the question. When document evidence is supplied, use only that evidence. "
    "When no document evidence is supplied, answer only from your existing knowledge and "
    "do not claim or imply document support. If the available basis does not adequately "
    "support an answer, return status='insufficient_evidence' and answer=null. Cite only "
    "supplied 1-based physical PDF page numbers; when no document evidence is supplied, "
    "cited_pages must be empty. Return one object matching response_schema."
)

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["answer", "cited_pages", "status"],
    "properties": {
        "answer": {"type": ["string", "null"]},
        "cited_pages": {
            "type": "array",
            "items": {"type": "integer", "minimum": 1},
        },
        "status": {
            "type": "string",
            "enum": ["answerable", "insufficient_evidence"],
        },
    },
}


@dataclass(frozen=True)
class EvidencePage:
    """One page exposed to the future reasoning model."""

    page: int
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {"page": self.page, "text": self.text}


@dataclass(frozen=True)
class ReasoningInput:
    """Experiment metadata plus the condition-blind payload sent to a model."""

    question_id: str
    doc_id: str
    condition: str
    question: str
    evidence: tuple[EvidencePage, ...]
    instructions: str = DRAFT_INSTRUCTIONS

    def model_input(self) -> dict[str, Any]:
        """Return only fields that a reasoning model is allowed to see."""
        return {
            "instructions": self.instructions,
            "question": self.question,
            "evidence": [item.to_dict() for item in self.evidence],
            "response_schema": RESPONSE_SCHEMA,
        }

    def to_experiment_record(self) -> dict[str, Any]:
        """Return auditable metadata around the condition-blind model input."""
        return {
            "schema_version": 1,
            "question_id": self.question_id,
            "doc_id": self.doc_id,
            "condition": self.condition,
            "evidence_pages": [item.page for item in self.evidence],
            "model_input": self.model_input(),
        }


def _page_lookup(records: Sequence[PageRecord], doc_id: str) -> dict[int, PageRecord]:
    if not records:
        raise ValueError("at least one Page Record is required")
    if any(record.doc_id != doc_id for record in records):
        raise ValueError("Page Records contain a different document")
    lookup = {record.page: record for record in records}
    if len(lookup) != len(records):
        raise ValueError("Page Records contain duplicate page numbers")
    return lookup


def _question_identity(question_record: dict[str, Any]) -> tuple[str, str, str]:
    question_id = question_record.get("id")
    question = question_record.get("question")
    pdf = question_record.get("pdf")
    if not isinstance(question_id, str) or not question_id:
        raise ValueError("question record must contain a non-empty id")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question record must contain a non-empty question")
    if not isinstance(pdf, dict) or not isinstance(pdf.get("doc_id_str"), str):
        raise ValueError("question record must contain pdf.doc_id_str")
    return question_id, pdf["doc_id_str"], question


def _oracle_pages(question_record: dict[str, Any]) -> list[int]:
    answer = question_record.get("answer")
    if not isinstance(answer, dict) or not isinstance(answer.get("is_answerable"), bool):
        raise ValueError("question record must contain answer.is_answerable")
    if not answer["is_answerable"]:
        return []
    evidences = question_record.get("evidences")
    if not isinstance(evidences, list) or not evidences:
        raise ValueError("answerable question must contain evidence records")
    pages = []
    for evidence in evidences:
        page = evidence.get("page") if isinstance(evidence, dict) else None
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise ValueError("evidence page must be a positive integer")
        pages.append(page)
    return sorted(set(pages))


def build_reasoning_input(
    question_record: dict[str, Any],
    page_records: Sequence[PageRecord],
    *,
    condition: str,
    retrieved_pages: Sequence[int] | None = None,
    top_k: int | None = None,
    instructions: str = DRAFT_INSTRUCTIONS,
) -> ReasoningInput:
    """Build one condition input without exposing the gold answer."""
    if condition not in SUPPORTED_CONDITIONS:
        raise ValueError(f"condition must be one of {SUPPORTED_CONDITIONS}")
    if not isinstance(instructions, str) or not instructions.strip():
        raise ValueError("instructions must be a non-empty string")
    question_id, doc_id, question = _question_identity(question_record)

    if condition == CLOSED_BOOK:
        if retrieved_pages is not None or top_k is not None:
            raise ValueError("closed_book does not accept retrieved_pages or top_k")
        selected_pages: list[int] = []
        lookup: dict[int, PageRecord] = {}
    elif condition == REAL_RETRIEVAL:
        lookup = _page_lookup(page_records, doc_id)
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
            raise ValueError("real_retrieval requires a positive integer top_k")
        if retrieved_pages is None:
            raise ValueError("real_retrieval requires retrieved_pages")
        selected_pages = list(retrieved_pages[:top_k])
        if len(selected_pages) != top_k:
            raise ValueError("retrieved_pages contains fewer pages than top_k")
        if len(selected_pages) != len(set(selected_pages)):
            raise ValueError("retrieved_pages contains duplicate pages within top_k")
    else:
        lookup = _page_lookup(page_records, doc_id)
        if retrieved_pages is not None or top_k is not None:
            raise ValueError("oracle_page does not accept retrieved_pages or top_k")
        selected_pages = _oracle_pages(question_record)

    evidence: list[EvidencePage] = []
    for page in selected_pages:
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise ValueError("selected page must be a positive integer")
        if page not in lookup:
            raise ValueError(f"selected page is absent from the Page Records: {page}")
        evidence.append(EvidencePage(page=page, text=lookup[page].text))

    return ReasoningInput(
        question_id=question_id,
        doc_id=doc_id,
        condition=condition,
        question=question,
        evidence=tuple(evidence),
        instructions=instructions,
    )


def build_reasoning_pair(
    question_record: dict[str, Any],
    page_records: Sequence[PageRecord],
    retrieved_pages: Sequence[int],
    *,
    top_k: int,
) -> tuple[ReasoningInput, ReasoningInput]:
    """Build paired real-retrieval and Oracle-Page inputs for one question."""
    real = build_reasoning_input(
        question_record,
        page_records,
        condition=REAL_RETRIEVAL,
        retrieved_pages=retrieved_pages,
        top_k=top_k,
    )
    oracle = build_reasoning_input(
        question_record,
        page_records,
        condition=ORACLE_PAGE,
    )
    return real, oracle


def build_reasoning_triplet(
    question_record: dict[str, Any],
    page_records: Sequence[PageRecord],
    retrieved_pages: Sequence[int],
    *,
    top_k: int,
) -> tuple[ReasoningInput, ReasoningInput, ReasoningInput]:
    """Build matched C0/C1/C2 pilot inputs with one shared prompt contract."""
    closed = build_reasoning_input(
        question_record,
        (),
        condition=CLOSED_BOOK,
        instructions=PILOT_INSTRUCTIONS_V1,
    )
    real = build_reasoning_input(
        question_record,
        page_records,
        condition=REAL_RETRIEVAL,
        retrieved_pages=retrieved_pages,
        top_k=top_k,
        instructions=PILOT_INSTRUCTIONS_V1,
    )
    oracle = build_reasoning_input(
        question_record,
        page_records,
        condition=ORACLE_PAGE,
        instructions=PILOT_INSTRUCTIONS_V1,
    )
    return closed, real, oracle


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--retrieval-results", required=True, type=Path)
    parser.add_argument("--question-id", required=True)
    parser.add_argument("--top-k", required=True, type=int)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--include-closed-book", action="store_true")
    args = parser.parse_args()

    questions = {record["id"]: record for record in load_records(args.benchmark, split="dev")}
    if args.question_id not in questions:
        raise ValueError("question ID is absent from guarded dev records")
    result = json.loads(args.retrieval_results.read_text(encoding="utf-8"))
    if result.get("split") != "development_tune":
        raise ValueError("retrieval result is not development_tune")
    result_by_id = {item["question_id"]: item for item in result["per_question"]}
    if args.question_id not in result_by_id:
        raise ValueError("question ID is absent from the tune retrieval result")

    page_records = read_page_records_jsonl(args.corpus)
    if args.include_closed_book:
        closed, real, oracle = build_reasoning_triplet(
            questions[args.question_id],
            page_records,
            result_by_id[args.question_id]["retrieved_pages"],
            top_k=args.top_k,
        )
        write_json(args.output_dir / "closed_book.json", closed.to_experiment_record())
    else:
        real, oracle = build_reasoning_pair(
            questions[args.question_id],
            page_records,
            result_by_id[args.question_id]["retrieved_pages"],
            top_k=args.top_k,
        )
    write_json(args.output_dir / "real_retrieval.json", real.to_experiment_record())
    write_json(args.output_dir / "oracle_page.json", oracle.to_experiment_record())
    print(
        json.dumps(
            {
                "question_id": args.question_id,
                "top_k": args.top_k,
                "real_retrieval_pages": [item.page for item in real.evidence],
                "oracle_pages": [item.page for item in oracle.evidence],
                "closed_book_included": args.include_closed_book,
                "output_dir": str(args.output_dir),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
