"""Pinned ColSmol visual-document encoder with offline snapshot enforcement."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import numpy as np
from numpy.typing import NDArray


COLSMOL_256M_MODEL_ID = "vidore/colSmol-256M"
COLSMOL_256M_REVISION = "c79b633e17e060cc109b11aa2bf92a1517d3bd6f"
COLSMOL_256M_BASE_MODEL_ID = "vidore/ColSmolVLM-Instruct-256M-base"
COLSMOL_256M_BASE_REVISION = "99ca96f1f6b95b3a69e6abef74a2416cb738fed0"


def _snapshot_path(cache_root: Path, repository: str, revision: str) -> Path:
    return cache_root / repository / "snapshots" / revision


def resolve_colsmol_model_source(
    cache_folder: str | None,
    *,
    local_files_only: bool,
) -> str:
    """Resolve the pinned adapter snapshot without an accidental network lookup."""
    if not local_files_only:
        return COLSMOL_256M_MODEL_ID
    if cache_folder is None:
        raise RuntimeError("offline visual loading requires cache_folder")
    root = Path(cache_folder)
    repository = "models--vidore--colSmol-256M"
    candidates = (
        _snapshot_path(root, repository, COLSMOL_256M_REVISION),
        _snapshot_path(root / "hub", repository, COLSMOL_256M_REVISION),
    )
    for candidate in candidates:
        if (candidate / "modules.json").is_file():
            return str(candidate)
    raise RuntimeError("pinned ColSmol adapter snapshot is not available in the local cache")


def validate_colsmol_base_snapshot(cache_folder: str | None) -> Path:
    """Require the exact base checkpoint resolved during preregistration."""
    if cache_folder is None:
        raise RuntimeError("visual loading requires cache_folder")
    root = Path(cache_folder)
    repository = "models--vidore--ColSmolVLM-Instruct-256M-base"
    candidates = (
        _snapshot_path(root, repository, COLSMOL_256M_BASE_REVISION),
        _snapshot_path(root / "hub", repository, COLSMOL_256M_BASE_REVISION),
    )
    for candidate in candidates:
        if (candidate / "config.json").is_file() and (candidate / "model.safetensors").is_file():
            return candidate
    raise RuntimeError("pinned ColSmol base snapshot is not available in the local cache")


class SentenceTransformerColSmolEncoder:
    """Encode questions and rendered pages as ColBERT-style multi-vector arrays."""

    def __init__(
        self,
        cache_folder: str,
        *,
        device: str = "cpu",
        local_files_only: bool = True,
    ):
        try:
            from sentence_transformers import MultiVectorEncoder
        except ImportError as error:  # pragma: no cover - dependency is pinned
            raise RuntimeError("sentence-transformers>=6 with image extras is required") from error

        if local_files_only:
            validate_colsmol_base_snapshot(cache_folder)
        model_source = resolve_colsmol_model_source(
            cache_folder,
            local_files_only=local_files_only,
        )
        kwargs: dict[str, Any] = {
            "cache_folder": cache_folder,
            "device": device,
            "local_files_only": local_files_only,
        }
        if model_source == COLSMOL_256M_MODEL_ID:
            kwargs["revision"] = COLSMOL_256M_REVISION
        self.model = MultiVectorEncoder(model_source, **kwargs)

    def encode_query(self, query: str) -> NDArray[np.float32]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        values = self.model.encode_query(
            [query],
            batch_size=1,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.asarray(values[0], dtype=np.float32)

    def encode_pages(
        self,
        pages: Sequence[Any],
        *,
        batch_size: int = 1,
    ) -> list[NDArray[np.float32]]:
        if not pages:
            raise ValueError("at least one rendered page is required")
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
            raise ValueError("batch_size must be a positive integer")
        values = self.model.encode_document(
            list(pages),
            batch_size=batch_size,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        if len(values) != len(pages):
            raise RuntimeError("visual encoder did not return one embedding per page")
        return [np.asarray(value, dtype=np.float32) for value in values]
