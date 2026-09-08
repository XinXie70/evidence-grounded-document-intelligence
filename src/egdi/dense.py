"""Deterministic dense retrieval with within-page chunking and page aggregation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol, Sequence

import numpy as np
from numpy.typing import NDArray

from .text import PageRecord


BGE_SMALL_EN_V1_5_MODEL_ID = "BAAI/bge-small-en-v1.5"
BGE_SMALL_EN_V1_5_REVISION = "baab320e3049c6c62dd63560765566dd9083985e"
BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


class DenseEncoder(Protocol):
    """Minimal encoder contract used by the retrieval index."""

    def split_text(self, text: str, chunk_tokens: int, overlap_tokens: int) -> list[str]: ...

    def encode_passages(self, texts: Sequence[str]) -> NDArray[np.floating]: ...

    def encode_query(self, query: str) -> NDArray[np.floating]: ...


@dataclass(frozen=True)
class DenseChunk:
    doc_id: str
    page: int
    chunk_index: int
    text: str
    extraction_status: str


@dataclass(frozen=True)
class DenseResult:
    doc_id: str
    page: int
    score: float
    best_chunk_index: int
    extraction_status: str

    def to_dict(self) -> dict[str, str | int | float]:
        return asdict(self)


def _normalized_rows(values: NDArray[np.floating]) -> NDArray[np.float64]:
    matrix = np.asarray(values, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[1] == 0:
        raise ValueError("passage embeddings must be a non-empty 2D matrix")
    if not np.isfinite(matrix).all():
        raise ValueError("passage embeddings must be finite")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return np.divide(matrix, norms, out=np.zeros_like(matrix), where=norms != 0)


def _normalized_vector(values: NDArray[np.floating], dimension: int) -> NDArray[np.float64]:
    vector = np.asarray(values, dtype=np.float64)
    if vector.ndim != 1 or vector.shape[0] != dimension:
        raise ValueError("query embedding dimension must match passage embeddings")
    if not np.isfinite(vector).all():
        raise ValueError("query embedding must be finite")
    norm = np.linalg.norm(vector)
    return vector / norm if norm else np.zeros_like(vector)


class PageDenseIndex:
    """Dense chunk index whose scored output unit is one physical PDF page."""

    def __init__(
        self,
        records: Sequence[PageRecord],
        encoder: DenseEncoder,
        *,
        chunk_tokens: int = 256,
        overlap_tokens: int = 0,
    ):
        if not records:
            raise ValueError("at least one PageRecord is required")
        if isinstance(chunk_tokens, bool) or not isinstance(chunk_tokens, int) or chunk_tokens < 1:
            raise ValueError("chunk_tokens must be a positive integer")
        if (
            isinstance(overlap_tokens, bool)
            or not isinstance(overlap_tokens, int)
            or overlap_tokens < 0
            or overlap_tokens >= chunk_tokens
        ):
            raise ValueError("overlap_tokens must be an integer from 0 to chunk_tokens - 1")
        identities = [(record.doc_id, record.page) for record in records]
        if len(identities) != len(set(identities)):
            raise ValueError("PageRecord identities must be unique")

        self.records = list(records)
        self.encoder = encoder
        self.chunk_tokens = chunk_tokens
        self.overlap_tokens = overlap_tokens
        self.chunks: list[DenseChunk] = []
        for record in self.records:
            chunk_texts = encoder.split_text(record.text, chunk_tokens, overlap_tokens)
            if not chunk_texts:
                chunk_texts = [""]
            for chunk_index, text in enumerate(chunk_texts):
                self.chunks.append(
                    DenseChunk(
                        doc_id=record.doc_id,
                        page=record.page,
                        chunk_index=chunk_index,
                        text=text,
                        extraction_status=record.extraction_status,
                    )
                )

        embeddings = encoder.encode_passages([chunk.text for chunk in self.chunks])
        if len(embeddings) != len(self.chunks):
            raise ValueError("encoder must return one embedding per passage")
        self.chunk_embeddings = _normalized_rows(embeddings)

    def search(self, query: str, top_k: int) -> list[DenseResult]:
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
            raise ValueError("top_k must be a positive integer")
        if not isinstance(query, str):
            raise TypeError("query must be a string")
        if not query.strip():
            return []

        query_embedding = _normalized_vector(
            self.encoder.encode_query(query), self.chunk_embeddings.shape[1]
        )
        chunk_scores = self.chunk_embeddings @ query_embedding
        best_by_page: dict[tuple[str, int], tuple[DenseChunk, float]] = {}
        for chunk, score_value in zip(self.chunks, chunk_scores, strict=True):
            score = float(score_value)
            identity = (chunk.doc_id, chunk.page)
            previous = best_by_page.get(identity)
            if previous is None or score > previous[1]:
                best_by_page[identity] = (chunk, score)

        ranked = sorted(
            best_by_page.values(),
            key=lambda item: (-item[1], item[0].doc_id, item[0].page),
        )[: min(top_k, len(best_by_page))]
        return [
            DenseResult(
                doc_id=chunk.doc_id,
                page=chunk.page,
                score=score,
                best_chunk_index=chunk.chunk_index,
                extraction_status=chunk.extraction_status,
            )
            for chunk, score in ranked
        ]


class SentenceTransformerBgeEncoder:
    """Pinned BGE-small encoder with tokenizer-aligned deterministic chunks."""

    def __init__(self, cache_folder: str | None = None, *, device: str = "cpu"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as error:  # pragma: no cover - environment-specific message
            raise RuntimeError("sentence-transformers is required for dense retrieval") from error
        self.model = SentenceTransformer(
            BGE_SMALL_EN_V1_5_MODEL_ID,
            revision=BGE_SMALL_EN_V1_5_REVISION,
            cache_folder=cache_folder,
            device=device,
        )
        self.tokenizer = self.model.tokenizer

    def split_text(self, text: str, chunk_tokens: int, overlap_tokens: int) -> list[str]:
        special_tokens = self.tokenizer.num_special_tokens_to_add(pair=False)
        content_tokens = chunk_tokens - special_tokens
        if content_tokens < 1:
            raise ValueError("chunk_tokens must leave room for model special tokens")
        if overlap_tokens >= content_tokens:
            raise ValueError("overlap_tokens must be smaller than the content token capacity")
        token_ids = self.tokenizer(
            text,
            add_special_tokens=False,
            truncation=False,
            return_attention_mask=False,
            return_token_type_ids=False,
            verbose=False,
        )["input_ids"]
        if not token_ids:
            return [""]
        step = content_tokens - overlap_tokens
        return [
            self.tokenizer.decode(
                token_ids[start : start + content_tokens],
                skip_special_tokens=True,
                clean_up_tokenization_spaces=True,
            )
            for start in range(0, len(token_ids), step)
        ]

    def encode_passages(self, texts: Sequence[str]) -> NDArray[np.floating]:
        return self.model.encode(
            list(texts),
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

    def encode_query(self, query: str) -> NDArray[np.floating]:
        encoded = self.model.encode(
            BGE_QUERY_INSTRUCTION + query,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(encoded)
