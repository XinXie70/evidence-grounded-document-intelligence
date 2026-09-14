"""Question-conditioned visual page scoring with ColBERT-style late interaction."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class VisualPageScore:
    """One visually reranked page with reversible original-rank provenance."""

    page: int
    score: float
    original_rank: int

    def to_dict(self) -> dict[str, int | float]:
        return asdict(self)


def _normalized_rows(values: NDArray[np.floating], *, label: str) -> NDArray[np.float64]:
    matrix = np.asarray(values, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise ValueError(f"{label} must be a non-empty 2D matrix")
    if not np.isfinite(matrix).all():
        raise ValueError(f"{label} must contain only finite values")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return np.divide(matrix, norms, out=np.zeros_like(matrix), where=norms != 0)


def late_interaction_score(
    query_embedding: NDArray[np.floating],
    document_embedding: NDArray[np.floating],
) -> float:
    """Return the sum of each query vector's best cosine match to a page vector."""
    query = _normalized_rows(query_embedding, label="query_embedding")
    document = _normalized_rows(document_embedding, label="document_embedding")
    if query.shape[1] != document.shape[1]:
        raise ValueError("query and document embedding dimensions must match")
    token_to_patch = query @ document.T
    return float(token_to_patch.max(axis=1).sum())


def rerank_visual_pages(
    candidate_pages: Sequence[int],
    query_embedding: NDArray[np.floating],
    page_embeddings: Mapping[int, NDArray[np.floating]],
) -> list[VisualPageScore]:
    """Rerank one RRF page pool by visual relevance, preserving RRF order on exact ties."""
    if not candidate_pages:
        raise ValueError("candidate_pages must be non-empty")
    if any(isinstance(page, bool) or not isinstance(page, int) or page < 1 for page in candidate_pages):
        raise ValueError("candidate_pages must contain positive integers")
    if len(candidate_pages) != len(set(candidate_pages)):
        raise ValueError("candidate_pages must be unique")
    if set(candidate_pages) != set(page_embeddings):
        raise ValueError("page_embeddings must cover exactly the candidate pages")

    scored = [
        VisualPageScore(
            page=page,
            score=late_interaction_score(query_embedding, page_embeddings[page]),
            original_rank=rank,
        )
        for rank, page in enumerate(candidate_pages, start=1)
    ]
    return sorted(scored, key=lambda item: (-item.score, item.original_rank))


def build_candidate_page_render_command(
    pdftoppm: str,
    pdf_path: Path,
    output_prefix: Path,
    physical_page: int,
    *,
    dpi: int = 150,
) -> list[str]:
    """Build a page-bounded Poppler command that emits one provenance-safe PNG."""
    if not isinstance(pdftoppm, str) or not pdftoppm.strip():
        raise ValueError("pdftoppm must be a non-empty executable path")
    if isinstance(physical_page, bool) or not isinstance(physical_page, int) or physical_page < 1:
        raise ValueError("physical_page must be a positive integer")
    if isinstance(dpi, bool) or not isinstance(dpi, int) or dpi < 1:
        raise ValueError("dpi must be a positive integer")
    return [
        pdftoppm,
        "-png",
        "-singlefile",
        "-f",
        str(physical_page),
        "-l",
        str(physical_page),
        "-r",
        str(dpi),
        str(pdf_path),
        str(output_prefix),
    ]
