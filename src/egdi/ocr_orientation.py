"""Select an OCR page orientation from auditable Tesseract TSV confidence."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .io import sha256_file, write_json


CARDINAL_ROTATIONS = (0, 90, 180, 270)
DEFAULT_RETRY_MEAN_CONFIDENCE_THRESHOLD = 40.0


def summarize_tesseract_tsv(tsv_text: str) -> dict[str, int | float]:
    """Summarize recognized words while excluding Tesseract's structural rows."""
    if not isinstance(tsv_text, str):
        raise TypeError("tsv_text must be a string")
    reader = csv.DictReader(tsv_text.splitlines(), delimiter="\t")
    if reader.fieldnames is None or not {"text", "conf"}.issubset(reader.fieldnames):
        raise ValueError("Tesseract TSV must contain text and conf columns")

    confidences: list[float] = []
    for row in reader:
        if not (row.get("text") or "").strip():
            continue
        try:
            confidence = float(row["conf"])
        except (TypeError, ValueError) as error:
            raise ValueError("Tesseract TSV contains a non-numeric confidence") from error
        if confidence >= 0:
            confidences.append(confidence)

    word_count = len(confidences)
    confidence_mass = sum(confidences)
    return {
        "word_count": word_count,
        "mean_confidence": confidence_mass / word_count if word_count else 0.0,
        "confidence_mass": confidence_mass,
        "high_confidence_word_count": sum(value >= 80 for value in confidences),
    }


def needs_orientation_retry(
    summary: Mapping[str, int | float],
    *,
    mean_confidence_threshold: float = DEFAULT_RETRY_MEAN_CONFIDENCE_THRESHOLD,
) -> bool:
    """Flag low-confidence original OCR for bounded cardinal-rotation retry."""
    if isinstance(mean_confidence_threshold, bool) or not isinstance(
        mean_confidence_threshold, (int, float)
    ):
        raise TypeError("mean_confidence_threshold must be numeric")
    if not 0 <= float(mean_confidence_threshold) <= 100:
        raise ValueError("mean_confidence_threshold must be between 0 and 100")
    mean_confidence = summary.get("mean_confidence")
    if isinstance(mean_confidence, bool) or not isinstance(
        mean_confidence, (int, float)
    ):
        raise ValueError("summary must contain numeric mean_confidence")
    return float(mean_confidence) < float(mean_confidence_threshold)


def select_best_orientation(
    tsv_by_rotation: Mapping[int, str],
    *,
    allowed_rotations: Sequence[int] = CARDINAL_ROTATIONS,
) -> dict[str, Any]:
    """Choose the highest confidence-mass OCR result with stable tie-breaking."""
    allowed = list(allowed_rotations)
    if not allowed or len(allowed) != len(set(allowed)):
        raise ValueError("allowed_rotations must be non-empty and unique")
    if any(rotation not in CARDINAL_ROTATIONS for rotation in allowed):
        raise ValueError("rotations must be one of 0, 90, 180, or 270 degrees")
    if set(tsv_by_rotation) != set(allowed):
        raise ValueError("TSV candidates must exactly match allowed_rotations")

    candidates = []
    for preference_rank, rotation in enumerate(allowed):
        summary = summarize_tesseract_tsv(tsv_by_rotation[rotation])
        candidates.append(
            {
                "rotation_degrees_clockwise": rotation,
                "preference_rank": preference_rank,
                **summary,
            }
        )
    ranked = sorted(
        candidates,
        key=lambda item: (
            -item["confidence_mass"],
            -item["mean_confidence"],
            -item["word_count"],
            item["preference_rank"],
        ),
    )
    return {
        "selected_rotation_degrees_clockwise": ranked[0][
            "rotation_degrees_clockwise"
        ],
        "selection_metric": "recognized_word_confidence_mass",
        "tie_break": "mean_confidence_then_word_count_then_rotation_preference",
        "candidates": candidates,
        "uses_gold_or_answer_labels": False,
    }


def _parse_candidate(value: str) -> tuple[int, Path]:
    rotation_text, separator, path_text = value.partition(":")
    if not separator or not path_text:
        raise argparse.ArgumentTypeError("candidate must use ROTATION:PATH")
    try:
        rotation = int(rotation_text)
    except ValueError as error:
        raise argparse.ArgumentTypeError("candidate rotation must be an integer") from error
    return rotation, Path(path_text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate",
        action="append",
        required=True,
        type=_parse_candidate,
        help="One OCR confidence file as ROTATION:PATH; repeat for each direction.",
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    paths: dict[int, Path] = {}
    for rotation, path in args.candidate:
        if rotation in paths:
            raise ValueError(f"duplicate rotation candidate: {rotation}")
        if not path.is_file():
            raise FileNotFoundError(f"TSV candidate does not exist: {path}")
        paths[rotation] = path
    allowed = [rotation for rotation in CARDINAL_ROTATIONS if rotation in paths]
    result = select_best_orientation(
        {rotation: paths[rotation].read_text(encoding="utf-8") for rotation in allowed},
        allowed_rotations=allowed,
    )
    result["inputs"] = [
        {
            "rotation_degrees_clockwise": rotation,
            "path": str(paths[rotation]),
            "sha256": sha256_file(paths[rotation]),
        }
        for rotation in allowed
    ]
    write_json(args.output, result)
    print(json.dumps({"output": str(args.output), **result}, indent=2))


if __name__ == "__main__":
    main()
