"""Deterministic question and document-clustered bootstrap intervals for final metrics."""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Sequence

from .io import sha256_file, write_json


DEFAULT_SEED = 20260827
DEFAULT_REPLICATES = 10_000


def _mean(values: Sequence[bool | float]) -> float | None:
    return None if not values else sum(float(value) for value in values) / len(values)


def evaluation_metrics(rows: Sequence[dict[str, Any]]) -> dict[str, float | None]:
    if not rows:
        raise ValueError("at least one evaluation row is required")
    answered = [row for row in rows if row.get("prediction_status") == "answerable"]
    retrieval = [
        row["page_diagnostics"]
        for row in rows
        if isinstance(row.get("page_diagnostics"), dict)
        and row["page_diagnostics"].get("retrieval_scoring_eligible") is True
    ]
    for field in ("task_correct", "grounded_correct"):
        if any(not isinstance(row.get(field), bool) for row in rows):
            raise ValueError(f"every row must define boolean {field}")
    return {
        "task_accuracy": _mean([row["task_correct"] for row in rows]),
        "grounded_accuracy": _mean([row["grounded_correct"] for row in rows]),
        "coverage": len(answered) / len(rows),
        "selective_task_accuracy": _mean([row["task_correct"] for row in answered]),
        "selective_grounded_accuracy": _mean([row["grounded_correct"] for row in answered]),
        "any_evidence_recall": _mean([row["any_evidence_recall"] for row in retrieval]),
        "complete_evidence_recall": _mean(
            [row["complete_evidence_recall"] for row in retrieval]
        ),
    }


def _percentile(sorted_values: Sequence[float], probability: float) -> float:
    if not sorted_values:
        raise ValueError("percentile requires at least one value")
    position = (len(sorted_values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def _intervals(samples: Sequence[dict[str, float | None]]) -> dict[str, dict[str, Any]]:
    fields = samples[0]
    output = {}
    for field in fields:
        values = sorted(
            float(sample[field]) for sample in samples if sample[field] is not None
        )
        output[field] = {
            "lower": None if not values else _percentile(values, 0.025),
            "upper": None if not values else _percentile(values, 0.975),
            "valid_replicates": len(values),
        }
    return output


def _resample_questions(
    rows: Sequence[dict[str, Any]], rng: random.Random
) -> list[dict[str, Any]]:
    return [rows[rng.randrange(len(rows))] for _ in rows]


def _cluster_sampler(rows: Sequence[dict[str, Any]]) -> Callable[[random.Random], list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        doc_id = row.get("doc_id")
        if not isinstance(doc_id, str) or not doc_id:
            raise ValueError("every row must define a non-empty doc_id")
        grouped[doc_id].append(row)
    document_ids = sorted(grouped)

    def sample(rng: random.Random) -> list[dict[str, Any]]:
        selected = [document_ids[rng.randrange(len(document_ids))] for _ in document_ids]
        return [row for doc_id in selected for row in grouped[doc_id]]

    return sample


def bootstrap_evaluation(
    rows: Sequence[dict[str, Any]],
    *,
    replicates: int = DEFAULT_REPLICATES,
    seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    if isinstance(replicates, bool) or not isinstance(replicates, int) or replicates < 1:
        raise ValueError("replicates must be a positive integer")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    rows = list(rows)
    point = evaluation_metrics(rows)
    cluster_sample = _cluster_sampler(rows)
    question_rng = random.Random(seed)
    cluster_rng = random.Random(seed)
    question_samples = [
        evaluation_metrics(_resample_questions(rows, question_rng))
        for _ in range(replicates)
    ]
    cluster_samples = [
        evaluation_metrics(cluster_sample(cluster_rng)) for _ in range(replicates)
    ]
    return {
        "schema_version": 1,
        "status": "bootstrap_95_percent_intervals_complete",
        "question_count": len(rows),
        "document_count": len({row["doc_id"] for row in rows}),
        "replicates": replicates,
        "seed": seed,
        "point_estimates": point,
        "question_bootstrap_95_ci": _intervals(question_samples),
        "document_clustered_bootstrap_95_ci": _intervals(cluster_samples),
        "interval_method": "percentile",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--replicates", type=int, default=DEFAULT_REPLICATES)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite bootstrap result: {args.output}")
    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    rows = audit.get("cases") if isinstance(audit, dict) else None
    if not isinstance(rows, list):
        raise ValueError("audit must contain a case list")
    result = bootstrap_evaluation(rows, replicates=args.replicates, seed=args.seed)
    result["split"] = audit.get("split")
    result["audit_sha256"] = sha256_file(args.audit)
    write_json(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
