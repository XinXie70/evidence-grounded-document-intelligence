"""Deterministic page-level BM25 baseline."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from .text import PageRecord, tokenize_for_bm25


QUERY_TOKEN_POLICIES = ("retain_repetitions", "deduplicate_preserve_order")


def prepare_query_tokens(query: str, policy: str = "retain_repetitions") -> list[str]:
    """Tokenize a query under one explicit, deterministic repetition policy."""
    if policy not in QUERY_TOKEN_POLICIES:
        raise ValueError(f"unsupported query token policy: {policy}")
    tokens = tokenize_for_bm25(query)
    if policy == "deduplicate_preserve_order":
        return list(dict.fromkeys(tokens))
    return tokens


@dataclass(frozen=True)
class Bm25Result:
    doc_id: str
    page: int
    score: float
    extraction_status: str

    def to_dict(self) -> dict[str, str | int | float]:
        return asdict(self)


class PageBm25Index:
    """An in-memory BM25 index whose retrieval unit is one physical PDF page."""

    def __init__(
        self,
        records: Sequence[PageRecord],
        k1: float = 1.2,
        b: float = 0.75,
        query_token_policy: str = "retain_repetitions",
    ):
        if not records:
            raise ValueError("at least one PageRecord is required")
        if k1 <= 0:
            raise ValueError("k1 must be positive")
        if not 0 <= b <= 1:
            raise ValueError("b must be between 0 and 1")
        if query_token_policy not in QUERY_TOKEN_POLICIES:
            raise ValueError(f"unsupported query token policy: {query_token_policy}")
        identities = [(record.doc_id, record.page) for record in records]
        if len(identities) != len(set(identities)):
            raise ValueError("PageRecord identities must be unique")

        self.records = list(records)
        self.k1 = float(k1)
        self.b = float(b)
        self.query_token_policy = query_token_policy
        self.term_frequencies = [Counter(tokenize_for_bm25(record.text)) for record in records]
        self.document_lengths = [sum(frequencies.values()) for frequencies in self.term_frequencies]
        self.average_document_length = sum(self.document_lengths) / len(self.document_lengths)
        self.document_frequencies: Counter[str] = Counter()
        for frequencies in self.term_frequencies:
            self.document_frequencies.update(frequencies.keys())

    def _idf(self, term: str) -> float:
        document_count = len(self.records)
        document_frequency = self.document_frequencies.get(term, 0)
        return math.log(
            1.0 + (document_count - document_frequency + 0.5) / (document_frequency + 0.5)
        )

    def search(self, query: str, top_k: int) -> list[Bm25Result]:
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
            raise ValueError("top_k must be a positive integer")
        query_tokens = prepare_query_tokens(query, self.query_token_policy)
        if not query_tokens:
            return []

        scores: list[float] = []
        average_length = self.average_document_length or 1.0
        for frequencies, document_length in zip(
            self.term_frequencies, self.document_lengths, strict=True
        ):
            score = 0.0
            for term in query_tokens:
                term_frequency = frequencies.get(term, 0)
                if term_frequency == 0:
                    continue
                length_normalization = self.k1 * (
                    1.0 - self.b + self.b * document_length / average_length
                )
                score += self._idf(term) * (
                    term_frequency * (self.k1 + 1.0)
                    / (term_frequency + length_normalization)
                )
            scores.append(score)

        ranked = sorted(
            zip(self.records, scores, strict=True),
            key=lambda item: (-item[1], item[0].doc_id, item[0].page),
        )[: min(top_k, len(self.records))]
        return [
            Bm25Result(
                doc_id=record.doc_id,
                page=record.page,
                score=score,
                extraction_status=record.extraction_status,
            )
            for record, score in ranked
        ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--query", required=True)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--k1", type=float, default=1.2)
    parser.add_argument("--b", type=float, default=0.75)
    parser.add_argument(
        "--query-token-policy",
        choices=QUERY_TOKEN_POLICIES,
        default="retain_repetitions",
    )
    args = parser.parse_args()

    from .corpus import read_page_records_jsonl

    records = read_page_records_jsonl(args.corpus)
    index = PageBm25Index(
        records,
        k1=args.k1,
        b=args.b,
        query_token_policy=args.query_token_policy,
    )
    results = index.search(args.query, top_k=args.top_k)
    print(
        json.dumps(
            {
                "query": args.query,
                "pages_indexed": len(records),
                "average_page_tokens": index.average_document_length,
                "k1": index.k1,
                "b": index.b,
                "query_token_policy": index.query_token_policy,
                "results": [result.to_dict() for result in results],
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
