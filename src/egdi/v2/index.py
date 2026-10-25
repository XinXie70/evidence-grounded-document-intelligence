"""Per-document hybrid retrieval: V1 BM25 + BGE dense fused with RRF.

The pipeline is the frozen V1 one (each retriever contributes its top 10 pages, RRF
constant 60); only the packaging per document and the snippet are new.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from egdi.bm25 import PageBm25Index
from egdi.corpus import read_page_records_jsonl
from egdi.dense import PageDenseIndex, SentenceTransformerBgeEncoder
from egdi.rrf import reciprocal_rank_fusion
from egdi.text import PageRecord, normalize_whitespace

PAGE_RECORD_DIRS = (
    "data/derived/page_records",
    "data/derived/page_records_calibration_v1",
    "data/derived/page_records_locked_test_v1",
)
MODEL_CACHE = "models/huggingface"
RRF_DEPTH = 10
RRF_CONSTANT = 60
CHUNK_TOKENS = 256
SNIPPET_CHARS = 300


def find_page_records(root: Path, doc_id: str) -> Path:
    for directory in PAGE_RECORD_DIRS:
        candidate = root / directory / f"{doc_id}.jsonl"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"no page records for document {doc_id}")


@lru_cache(maxsize=1)
def shared_encoder(model_cache: str = MODEL_CACHE) -> SentenceTransformerBgeEncoder:
    """Load the pinned BGE model once per process (offline)."""
    return SentenceTransformerBgeEncoder(cache_folder=model_cache, local_files_only=True)


class DocumentIndex:
    """Searchable view of one document; the retrieval unit is a 1-based PDF page."""

    def __init__(self, records: list[PageRecord], encoder: Any):
        doc_ids = {record.doc_id for record in records}
        if len(doc_ids) != 1:
            raise ValueError("DocumentIndex needs the pages of exactly one document")
        self.doc_id = doc_ids.pop()
        self.records = list(records)
        self.page_text = {record.page: record.text for record in records}
        self.page_count = max(self.page_text)
        self._bm25 = PageBm25Index(records)
        self._dense = PageDenseIndex(records, encoder, chunk_tokens=CHUNK_TOKENS, overlap_tokens=0)
        self._chunk_text = {(c.page, c.chunk_index): c.text for c in self._dense.chunks}

    @classmethod
    def load(cls, root: Path, doc_id: str, encoder: Any | None = None) -> "DocumentIndex":
        records = read_page_records_jsonl(find_page_records(root, doc_id))
        return cls(records, encoder or shared_encoder(str(root / MODEL_CACHE)))

    def search(self, query: str, k: int) -> list[dict[str, Any]]:
        """Top-k pages as ``{page, score, snippet}``; score is the RRF score."""
        bm25_pages = [hit.page for hit in self._bm25.search(query, RRF_DEPTH)]
        dense_hits = self._dense.search(query, len(self.records))
        dense_pages = [hit.page for hit in dense_hits[:RRF_DEPTH]]
        best_chunk = {hit.page: hit.best_chunk_index for hit in dense_hits}
        fused = reciprocal_rank_fusion(
            [bm25_pages, dense_pages], rank_constant=RRF_CONSTANT, top_k=k
        )
        return [
            {
                "page": page,
                "score": round(score, 5),
                "snippet": self._snippet(page, best_chunk.get(page)),
            }
            for page, score in fused
        ]

    def _snippet(self, page: int, chunk_index: int | None) -> str:
        text = self._chunk_text.get((page, chunk_index)) if chunk_index is not None else None
        return normalize_whitespace(text or self.page_text[page])[:SNIPPET_CHARS]
