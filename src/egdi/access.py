"""Benchmark loading with an explicit locked-test access guard."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .constants import LOCKED_TEST_ACK, LOCKED_TEST_ENV


class LockedTestAccessError(RuntimeError):
    pass


def require_evaluation_split_access(split: str) -> None:
    """Require explicit acknowledgement before any locked-test processing."""
    if split not in {"development_tune", "development_calibration", "locked_test"}:
        raise ValueError("unknown evaluation split")
    if split == "locked_test" and os.environ.get(LOCKED_TEST_ENV) != LOCKED_TEST_ACK:
        raise LockedTestAccessError(
            f"Locked test access denied. Set {LOCKED_TEST_ENV} to the exact documented "
            "acknowledgement only for the single frozen final evaluation."
        )


def load_records(benchmark_path: Path, split: str = "dev") -> list[dict[str, Any]]:
    """Load one official split; locked test requires a deliberate environment acknowledgement."""
    if split not in {"dev", "test"}:
        raise ValueError("split must be 'dev' or 'test'")
    if split == "test":
        require_evaluation_split_access("locked_test")
    records = json.loads(benchmark_path.read_text(encoding="utf-8"))
    return [record for record in records if record["split"] == split]


def load_for_day1_integrity_audit(benchmark_path: Path) -> list[dict[str, Any]]:
    """Load all labels only for deterministic integrity/split metadata generation."""
    records = json.loads(benchmark_path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("benchmark.json must contain a JSON array")
    return records
