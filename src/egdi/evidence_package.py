"""Retrieve ranked pages and package auditable evidence for grounded reasoning."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from .bm25 import QUERY_TOKEN_POLICIES, PageBm25Index
from .corpus import read_page_records_jsonl
from .io import sha256_file, write_json
from .reasoning_inputs import PILOT_INSTRUCTIONS_V1, REAL_RETRIEVAL, build_reasoning_input
from .text import PageRecord


CORPUS_KINDS = ("native_text", "ocr_text")
LAYOUT_TEXT_REPRESENTATION = "layout_preserved_ocr_text"
_OCR_PAGE_TEXT = re.compile(r"^page-(\d+)\.txt$")


def load_layout_texts(
    text_dir: Path, pages: Sequence[int]
) -> tuple[dict[int, str], list[dict[str, Any]]]:
    """Load selected raw OCR page texts without collapsing their line structure."""
    if not text_dir.is_dir():
        raise FileNotFoundError(f"OCR text directory does not exist: {text_dir}")
    if len(pages) != len(set(pages)):
        raise ValueError("layout-text pages must be unique")

    paths_by_page: dict[int, Path] = {}
    for path in text_dir.iterdir():
        match = _OCR_PAGE_TEXT.fullmatch(path.name)
        if match is None or not path.is_file():
            continue
        page = int(match.group(1))
        if page < 1:
            raise ValueError(f"OCR layout text has invalid page number: {path}")
        if page in paths_by_page:
            raise ValueError(f"duplicate OCR layout text for page {page}")
        paths_by_page[page] = path

    texts: dict[int, str] = {}
    audit: list[dict[str, Any]] = []
    for page in pages:
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise ValueError("layout-text page must be a positive integer")
        path = paths_by_page.get(page)
        if path is None:
            raise FileNotFoundError(
                f"OCR layout text does not exist for physical page {page} in {text_dir}"
            )
        text = path.read_text(encoding="utf-8").strip()
        texts[page] = text
        audit.append(
            {
                "page": page,
                "path": str(path),
                "sha256": sha256_file(path),
            }
        )
    return texts, audit


def build_evidence_package(
    question_id: str,
    question: str,
    records: Sequence[PageRecord],
    *,
    corpus_path: Path,
    corpus_kind: str,
    top_k: int = 3,
    k1: float = 1.2,
    b: float = 0.75,
    query_token_policy: str = "retain_repetitions",
) -> dict[str, Any]:
    """Build one label-free, ranked page package from a prepared corpus."""
    if not isinstance(question_id, str) or not question_id.strip():
        raise ValueError("question_id must be a non-empty string")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a non-empty string")
    if not records:
        raise ValueError("at least one Page Record is required")
    doc_ids = {record.doc_id for record in records}
    if len(doc_ids) != 1:
        raise ValueError("all Page Records must belong to one document")
    pages = [record.page for record in records]
    if pages != list(range(1, len(records) + 1)):
        raise ValueError("Page Records must be sequential from physical page 1")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= len(records):
        raise ValueError("top_k must be between 1 and the document page count")
    if corpus_kind not in CORPUS_KINDS:
        raise ValueError(f"corpus_kind must be one of {CORPUS_KINDS}")
    if not corpus_path.is_file():
        raise FileNotFoundError(f"corpus does not exist: {corpus_path}")

    index = PageBm25Index(
        records,
        k1=k1,
        b=b,
        query_token_policy=query_token_policy,
    )
    ranking = index.search(question, top_k=top_k)
    lookup = {record.page: record for record in records}
    evidence = [
        {
            "rank": rank,
            "page": result.page,
            "score": result.score,
            "extraction_status": result.extraction_status,
            "text": lookup[result.page].text,
        }
        for rank, result in enumerate(ranking, start=1)
    ]
    return {
        "schema_version": 1,
        "question_id": question_id,
        "doc_id": records[0].doc_id,
        "question": question,
        "corpus": {
            "kind": corpus_kind,
            "path": str(corpus_path),
            "sha256": sha256_file(corpus_path),
            "page_count": len(records),
        },
        "retrieval": {
            "method": "page_bm25",
            "k1": index.k1,
            "b": index.b,
            "query_token_policy": index.query_token_policy,
            "top_k": top_k,
        },
        "evidence_pages": [item["page"] for item in evidence],
        "evidence": evidence,
        "uses_gold_or_answer_labels": False,
    }


def build_real_retrieval_record(
    package: dict[str, Any],
    records: Sequence[PageRecord],
    *,
    evidence_text_by_page: Mapping[int, str] | None = None,
) -> dict[str, Any]:
    """Adapt one evidence package to the existing paid-reasoning input contract."""
    question_record = {
        "id": package["question_id"],
        "question": package["question"],
        "pdf": {"doc_id_str": package["doc_id"]},
    }
    reasoning = build_reasoning_input(
        question_record,
        records,
        condition=REAL_RETRIEVAL,
        retrieved_pages=package["evidence_pages"],
        top_k=package["retrieval"]["top_k"],
        instructions=PILOT_INSTRUCTIONS_V1,
    )
    experiment_record = reasoning.to_experiment_record()
    if evidence_text_by_page is not None:
        selected_pages = package["evidence_pages"]
        missing = [page for page in selected_pages if page not in evidence_text_by_page]
        if missing:
            raise ValueError(f"reasoning evidence text is missing pages: {missing}")
        for item in experiment_record["model_input"]["evidence"]:
            text = evidence_text_by_page[item["page"]]
            if not isinstance(text, str):
                raise TypeError("reasoning evidence text must be a string")
            item["text"] = text
        experiment_record["evidence_text_representation"] = (
            LAYOUT_TEXT_REPRESENTATION
        )
    return experiment_record


def write_evidence_outputs(
    output_dir: Path,
    package: dict[str, Any],
    real_retrieval: dict[str, Any],
) -> dict[str, Any]:
    """Atomically publish paired retrieval-audit and reasoning-input files."""
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite evidence output: {output_dir}")
    staging_dir = output_dir.with_name(output_dir.name + ".partial")
    if staging_dir.exists():
        raise FileExistsError(f"unfinished evidence staging output exists: {staging_dir}")
    staging_dir.mkdir(parents=True)
    package_path = staging_dir / "evidence_package.json"
    reasoning_path = staging_dir / "real_retrieval.json"
    write_json(package_path, package)
    write_json(reasoning_path, real_retrieval)
    summary = {
        "schema_version": 1,
        "question_id": package["question_id"],
        "evidence_pages": package["evidence_pages"],
        "evidence_package_sha256": sha256_file(package_path),
        "real_retrieval_sha256": sha256_file(reasoning_path),
    }
    write_json(staging_dir / "manifest.json", summary)
    staging_dir.replace(output_dir)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question-id", required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--corpus-kind", required=True, choices=CORPUS_KINDS)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--k1", type=float, default=1.2)
    parser.add_argument("--b", type=float, default=0.75)
    parser.add_argument(
        "--reasoning-text-dir",
        type=Path,
        help="Optional raw OCR text directory used only for LLM evidence context.",
    )
    parser.add_argument(
        "--query-token-policy",
        choices=QUERY_TOKEN_POLICIES,
        default="retain_repetitions",
    )
    args = parser.parse_args()
    records = read_page_records_jsonl(args.corpus)
    package = build_evidence_package(
        args.question_id,
        args.question,
        records,
        corpus_path=args.corpus,
        corpus_kind=args.corpus_kind,
        top_k=args.top_k,
        k1=args.k1,
        b=args.b,
        query_token_policy=args.query_token_policy,
    )
    evidence_text_by_page = None
    if args.reasoning_text_dir is not None:
        if args.corpus_kind != "ocr_text":
            raise ValueError("reasoning-text-dir is only valid for an OCR corpus")
        evidence_text_by_page, layout_audit = load_layout_texts(
            args.reasoning_text_dir, package["evidence_pages"]
        )
        package["reasoning_context"] = {
            "representation": LAYOUT_TEXT_REPRESENTATION,
            "pages": layout_audit,
        }
    real_retrieval = build_real_retrieval_record(
        package,
        records,
        evidence_text_by_page=evidence_text_by_page,
    )
    summary = write_evidence_outputs(args.output_dir, package, real_retrieval)
    print(json.dumps({"output_dir": str(args.output_dir), **summary}, indent=2))


if __name__ == "__main__":
    main()
