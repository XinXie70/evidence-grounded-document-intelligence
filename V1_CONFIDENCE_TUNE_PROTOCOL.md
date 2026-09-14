# V1 Confidence Tune Protocol

**Status:** frozen before current-pipeline outcome generation
**Date:** 2026-09-11
**Scope:** `development_tune` only; calibration and locked test remain closed

## Purpose

Determine whether label-free inference-time signals can rank current-system answers by their
probability of being correct and grounded. This is a bounded gate before calibration, not a final
benchmark run and not another retrieval-development loop.

## Fixed question set

Reuse the already frozen 24-document reliability selection in
`experiments/day4_reliability_pilot_selection_v0.json`:

- 24 questions from 24 document-disjoint `development_tune` documents;
- 18 benchmark-answerable and 6 benchmark-unanswerable questions;
- no question may be added, removed, or replaced after current-pipeline outputs are inspected;
- selection labels may be used only by the offline scorer, never by routing, retrieval, reasoning,
  or confidence-feature extraction.

The frozen label-free router assigns this set to:

| Route | Questions | Current V1 behavior |
|---|---:|---|
| R0 native text | 17 | equal-weight BM25 + pinned BGE RRF; Top-3 evidence |
| R1 local visual | 4 | question-conditioned ColSmol reranking of RRF Top-10; Top-3 evidence |
| R2 scanned document | 2 | frozen OCR candidate v2; 9--12 page windows |
| R3 document global | 1 | deterministic abstention; no evidence or paid request |

## Frozen retrieval and evidence rules

### R0

- native Page Records;
- BM25 `k1=1.2`, `b=0.75`, repeated query tokens retained;
- pinned `BAAI/bge-small-en-v1.5`, 256-token chunks, zero overlap, max chunk-to-page aggregation;
- equal-weight RRF with rank constant 60 and depth 10 per retriever;
- first three RRF pages become the evidence package.

### R1

- the same RRF Top-10 candidate set as R0;
- pinned question-conditioned ColSmol visual reranker from `visual_retrieval_v1`;
- first three visual-ranked pages become the evidence package;
- no benchmark evidence, crop, or per-question page rule is permitted.

### R2

- zero-native-text trigger only;
- frozen Tesseract and orientation-recovery provenance in
  `configs/r2_scanned_document_candidate_v2.json`;
- deduplicated query tokens, OCR BM25, three non-overlapping centered three-page windows;
- if the literal frozen em-dash separator is present, add at most one fully novel clause window;
- 9 pages normally and at most 12 pages; use layout-preserved OCR text.

### R3

- no partial Top-K claim for a document-global question;
- output `insufficient_evidence` locally without a paid model request.

## Reasoning batch

- Run only the current real-retrieval condition. Closed-book and Oracle Page are not repeated.
- Use one shared prompt, model configuration, output schema, zero-retry rule, and USD 1.00 hard
  cap per batch.
- The user must receive the conservative cost estimate and approve the paid batch before execution.
- Existing old-pipeline responses are evidence for history only and are not substituted for the
  current-pipeline batch.

## Confidence inputs

Permitted raw signals are those listed in `V1_COMPLETION_PROTOCOL.md` and implemented by
`src/egdi/confidence_features_v1.py`. Route-unavailable values must be represented as missing;
the implementation must not fabricate Dense/RRF values for R2 or any retrieval values for R3.

Post-generation hard eligibility requires all of:

1. response status is `answerable`;
2. output contract is valid;
3. citations remain within supplied context;
4. at least one citation is present.

## Outcome scoring frozen before inspection

For each question, the scorer records two labels:

- **task correct:** an answer matches the benchmark answer, or an unanswerable question is
  correctly rejected;
- **grounded correct:** task correct and every material claim needed for the answer is supported by
  its cited supplied pages.

Automatic checks cover schema validity, response status, citation presence, and citation scope.
Free-form answer equivalence and material-claim support use the same human-audit rubric as the
earlier reliability pilot. Human decisions must be recorded with an audit note and explicit user
confirmation; they cannot modify retrieval, features, or the model prompt.

## Keep/drop gate

After all predictions and raw features are frozen:

1. pair them with tune-only task and grounding labels;
2. define one deterministic scalar confidence formula, one missing-value rule, and stable
   `question_id` tie-breaking;
3. report risk-coverage, grounded-risk-coverage, AURC, ties, and 100/90/80/60 percent operating
   points;
4. open calibration only if higher confidence shows a useful directional association with grounded
   correctness and every signal is available on unseen questions.

If no useful generic ordering is found, document the negative result and stop. Do not add a
question-specific exception or inspect calibration to rescue the formula.
