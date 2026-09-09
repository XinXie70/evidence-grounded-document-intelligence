# Experiment Index

The repository preserves exploratory artifacts for provenance, but the project's main evidence
can be reviewed through the following short path.

Historical `dayN` prefixes are immutable experiment-batch identifiers, not claims that each phase
took one calendar day. They are retained so paths, checksums, and reproduction commands remain
stable. The index below uses capability-based phases for the public narrative.

## Phase 1 — Data and evaluation foundation

- [`../DAY1_REPORT.md`](../DAY1_REPORT.md) — pinned dataset, PDF validation, document-isolated
  splits, annotation audit, and text-layer audit.
- [`../DATA_AND_EVAL_PROTOCOL.md`](../DATA_AND_EVAL_PROTOCOL.md) — frozen eligibility, metrics,
  leakage controls, Oracle Evidence design, and cost rules.

## Phase 2 — Sparse retrieval baseline

- [`day2_bm25_tune_baseline_report.md`](day2_bm25_tune_baseline_report.md) — page-level BM25 on
  239 answerable development-tune questions; Complete Evidence Recall@10 = 70.71%.

## Phase 3 — Grounded reasoning and reliability

- [`day3_grounded_reasoning_smoke_v1_report.md`](day3_grounded_reasoning_smoke_v1_report.md) —
  initial same-model real-versus-Oracle evidence comparison.
- [`day4_reliability_pilot_report_v0.md`](day4_reliability_pilot_report_v0.md) — 24 questions and
  72 manually audited C0/C1/C2 conditions.

Condition definitions:

| Condition | Input to the reasoner | Purpose |
|---|---|---|
| C0 | Question only | Check whether the model guesses without evidence |
| C1 | Pages returned by real retrieval | Measure the deployed retrieval-to-answer path |
| C2 | Benchmark evidence pages | Estimate the reasoning ceiling when page retrieval is solved |
| C3 | Verified page/region images | Diagnose missing text and lost visual structure |
| C4 | Manually transcribed evidence facts | Isolate reasoning from visual parsing |

## Phase 4 — Failure-driven representation recovery

- [`day5_visual_recovery_report_v0.md`](day5_visual_recovery_report_v0.md) — bounded visual
  recovery for confirmed missing-text and layout failures.
- [`day5_r2_retrieval_evaluation_report_v0.md`](day5_r2_retrieval_evaluation_report_v0.md) —
  deterministic Tesseract OCR retrieval for documents with no native text layer.

## Phase 5 — Dense and hybrid retrieval

- [`day6_dense_grid_selection_report_v0.md`](day6_dense_grid_selection_report_v0.md) — frozen
  BGE-small 256-token, zero-overlap dense baseline.
- [`day6_bm25_dense_complementarity_report_v0.md`](day6_bm25_dense_complementarity_report_v0.md)
  — evidence that sparse and dense retrieval recover different pages.
- [`day6_hybrid_rrf_tune_report_v0.md`](day6_hybrid_rrf_tune_report_v0.md) — fixed equal-weight
  RRF hybrid; Complete Evidence Recall@10 = 77.41%.
- [`day6_dense_candidate_rerank_tune_report_v0.md`](day6_dense_candidate_rerank_tune_report_v0.md)
  — retained negative result showing that aggressive Top-2 dense reranking discards required
  multi-page evidence.

## Phase 6 — Reusable comparison pipeline

- [`day6_generic_fact_extraction_crossdoc_v0/score_citation_repaired_v0.json`](day6_generic_fact_extraction_crossdoc_v0/score_citation_repaired_v0.json)
  — scored method-development cases across document types.
- [`day6_generic_comparison_validation_v0/REPORT.md`](day6_generic_comparison_validation_v0/REPORT.md)
  — frozen six-document validation, exact answer match 4/6 and complete evidence match 5/6.

The final reusable path is:

```text
RRF Top-10 pages
  -> model extracts two ordered, cited numeric facts
  -> deterministic local arithmetic
  -> local numeric citation verification
  -> answer or explicit abstention
  -> benchmark scoring only after predictions are frozen
```

## Reading rule

Files named `candidate`, `probe`, `selection`, `audit`, or `smoke` are intermediate evidence,
not headline results. A report explicitly marked frozen or selected is the decision record. Failed
and negative experiments remain in the repository because they explain why the final pipeline has
its current shape.

## Phase 7 — Final ablation and stop decision

- [`day7_r1_visual_page_rerank_report_v0.md`](day7_r1_visual_page_rerank_report_v0.md) — binary
  PDF layout signals did not improve Complete Evidence Recall@3 or @5; the intervention was
  dropped and the portfolio MVP closed without calibration or locked-test claims.
