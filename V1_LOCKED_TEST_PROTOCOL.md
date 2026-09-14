# V1 One-Time Locked-Test Protocol

**Status:** frozen before locked-test access
**Date:** 2026-09-14 (Australia/Sydney)

## Purpose

Run the final V1 system once on the DocScope locked test after every inference and evaluation
component has been frozen. The run is evaluation-only: no observed test outcome may change V1.

## Access boundary

All locked-test preprocessing, selection, retrieval, visual ranking, reasoning, confidence, and
scoring entry points require:

```text
EGDI_ALLOW_LOCKED_TEST=I_UNDERSTAND_THIS_IS_THE_FINAL_LOCKED_TEST
```

The variable is not set during preflight. It is set only after the pre-test Git commit/tag, local
tests, component hashes, batch budgets, and explicit user authorization are complete.

## Frozen execution order

1. Verify the V1 system-freeze manifest and environment snapshot.
2. Open the test split once and write a label-free selection containing only question identity,
   document identity, and question text.
3. Generate and checksum native Page Records for all locked-test documents.
4. Run frozen BM25 + BGE dense retrieval and equal-weight RRF Top-10.
5. Apply the frozen R0/R1/R2/R3 routing policy, question-conditioned visual reranking for R1, and
   deterministic OCR package for R2.
6. Freeze evidence packages and partition answer-generation requests into independently resumable
   batches whose conservative hard cap is at most USD 1.00.
7. Run grounded answer generation once. R3 remains a local zero-cost abstention.
8. Freeze label-free post-generation confidence features and apply threshold
   0.3566666666666667. Save final predictions before reading answer or evidence labels.
9. Prepare semantic and evidence-support judge inputs, use the frozen judge partitioner to split
   calls into independently capped batches (target USD 0.95; hard cap USD 1.00), and run the pinned
   judges only after reminding the user of each batch budget.
10. Score task accuracy, grounded accuracy, coverage, selective accuracy, and evidence retrieval.
    Exclude the registered answerable-zero-evidence anomaly only from evidence-retrieval metrics.
11. Report question-bootstrap and document-clustered bootstrap 95% confidence intervals.
12. Preserve all outputs and failures. Do not tune, patch, rerun for correctness, or replace V1.

## Allowed operational recovery

An interrupted batch may resume from outputs whose input, request, and configuration hashes match.
A failed API response is preserved. A retry requires a separately recorded budget and may correct
only transport or incomplete-output failure; it may not depend on the apparent answer or score.

## Reporting boundary

All results, including abstentions, unsupported answers, retrieval failures, visual failures, and
uncertainty intervals, are reported. Per-question benchmark text, answers, evidence, PDFs, and judge
payloads remain local and are not committed to the public repository.
