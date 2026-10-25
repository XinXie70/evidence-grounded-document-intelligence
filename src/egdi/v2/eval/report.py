"""Metrics and paired document-level bootstrap over judged rows (V2_PLAN.md section 5)."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from egdi.bootstrap_evaluation import DEFAULT_REPLICATES, DEFAULT_SEED

# metric name -> predicate selecting the questions in its denominator
SLICES = {
    "task_accuracy": lambda r: True,  # all questions; abstaining on an answerable question is wrong
    "multi_page_task_accuracy": lambda r: r["answerable"] and r["multi_page"],  # the primary hypothesis
    "single_page_task_accuracy": lambda r: r["answerable"] and not r["multi_page"],
    "unanswerable_correct_abstention": lambda r: not r["answerable"],
    "answered_task_accuracy": lambda r: r["answered"],
    "grounded_accuracy": lambda r: True,
}
NUMERATOR = {"grounded_accuracy": "grounded_correct"}

COMPARISONS = (("A", "B0"), ("A", "B1"), ("B1", "B0"))
COMPARED_METRICS = (
    "multi_page_task_accuracy", "task_accuracy", "single_page_task_accuracy", "grounded_accuracy",
)


def point_estimates(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"questions": len(rows)}
    for name, keep in SLICES.items():
        chosen = [r for r in rows if keep(r)]
        field = NUMERATOR.get(name, "task_correct")
        out[name] = sum(r[field] for r in chosen) / len(chosen) if chosen else None
        out[name + "_n"] = len(chosen)
    out["coverage"] = sum(r["answered"] for r in rows) / len(rows)
    out["mean_cost_usd"] = sum(r["cost_usd"] for r in rows) / len(rows)
    out["mean_latency_s"] = sum(r["latency_s"] for r in rows) / len(rows)
    tool = [r["tool_calls"] for r in rows if r["tool_calls"] is not None]
    out["mean_tool_calls"] = sum(tool) / len(tool) if tool else None
    out["mean_pages_read"] = sum(len(r["pages_read"] or []) for r in rows) / len(rows)
    return out


def _document_arrays(rows_by_system: dict[str, list[dict]], systems: Sequence[str], metric: str):
    """Per-document numerators/denominators for each system over the questions all share."""
    shared = set.intersection(*({r["question_id"] for r in rows_by_system[s]} for s in systems))
    docs = sorted({r["doc_id"] for r in rows_by_system[systems[0]] if r["question_id"] in shared})
    index = {d: i for i, d in enumerate(docs)}
    field = NUMERATOR.get(metric, "task_correct")
    num = np.zeros((len(systems), len(docs)))
    den = np.zeros((len(systems), len(docs)))
    for k, system in enumerate(systems):
        for r in rows_by_system[system]:
            if r["question_id"] in shared and SLICES[metric](r):
                num[k, index[r["doc_id"]]] += r[field]
                den[k, index[r["doc_id"]]] += 1
    return num, den, len(shared)


def paired_bootstrap(
    rows_by_system: dict[str, list[dict[str, Any]]], system_a: str, system_b: str, metric: str,
    *, replicates: int = DEFAULT_REPLICATES, seed: int = DEFAULT_SEED,
) -> dict[str, Any]:
    """Difference (a - b) with a document-clustered percentile interval; same documents for both."""
    num, den, shared = _document_arrays(rows_by_system, [system_a, system_b], metric)
    rng = np.random.default_rng(seed)
    n_docs = num.shape[1]
    picks = rng.integers(0, n_docs, size=(replicates, n_docs))
    n_sum, d_sum = num[:, picks].sum(axis=2), den[:, picks].sum(axis=2)
    with np.errstate(invalid="ignore", divide="ignore"):
        rates = n_sum / d_sum
    diffs = rates[0] - rates[1]
    valid = diffs[~np.isnan(diffs)]
    totals = den.sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        observed = num.sum(axis=1) / totals
    return {
        "metric": metric, "a": system_a, "b": system_b, "questions": shared, "documents": n_docs,
        "rate_a": float(observed[0]), "rate_b": float(observed[1]),
        "difference": float(observed[0] - observed[1]),
        "ci95_lower": float(np.percentile(valid, 2.5)) if len(valid) else None,
        "ci95_upper": float(np.percentile(valid, 97.5)) if len(valid) else None,
        "valid_replicates": int(len(valid)), "replicates": replicates, "seed": seed,
    }


def build_report(
    rows: list[dict[str, Any]], *, replicates: int = DEFAULT_REPLICATES, seed: int = DEFAULT_SEED
) -> dict[str, Any]:
    by_system: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_system[row["system"]].append(row)
    report: dict[str, Any] = {
        "systems": {s: point_estimates(by_system[s]) for s in sorted(by_system)},
        "paired_comparisons": [],
        "document_count": len({r["doc_id"] for r in rows}),
    }
    for a, b in COMPARISONS:
        if a in by_system and b in by_system:
            for metric in COMPARED_METRICS:
                report["paired_comparisons"].append(
                    paired_bootstrap(by_system, a, b, metric, replicates=replicates, seed=seed)
                )
    return report


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{100 * value:.1f}%"


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "| system | n | task acc | multi-page | single-page | unanswerable abstain | grounded | coverage | $/q | s/q | tool calls | pages read |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for system, m in report["systems"].items():
        tools = "-" if m["mean_tool_calls"] is None else f"{m['mean_tool_calls']:.1f}"
        lines.append(
            f"| {system} | {m['questions']} | {_pct(m['task_accuracy'])} "
            f"| {_pct(m['multi_page_task_accuracy'])} ({m['multi_page_task_accuracy_n']}) "
            f"| {_pct(m['single_page_task_accuracy'])} ({m['single_page_task_accuracy_n']}) "
            f"| {_pct(m['unanswerable_correct_abstention'])} ({m['unanswerable_correct_abstention_n']}) "
            f"| {_pct(m['grounded_accuracy'])} | {_pct(m['coverage'])} | {m['mean_cost_usd']:.4f} "
            f"| {m['mean_latency_s']:.1f} | {tools} | {m['mean_pages_read']:.1f} |"
        )
    lines += ["", "| comparison | metric | a | b | difference | 95% CI (by document) |", "|---|---|---:|---:|---:|---|"]
    for c in report["paired_comparisons"]:
        lines.append(
            f"| {c['a']} - {c['b']} | {c['metric']} | {_pct(c['rate_a'])} | {_pct(c['rate_b'])} "
            f"| {100 * c['difference']:+.1f} pp | [{100 * c['ci95_lower']:+.1f}, {100 * c['ci95_upper']:+.1f}] |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judged", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--replicates", type=int, default=DEFAULT_REPLICATES)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.judged.read_text(encoding="utf-8").splitlines()]
    report = build_report(rows, replicates=args.replicates)
    print(render_markdown(report))
    if args.output:
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
