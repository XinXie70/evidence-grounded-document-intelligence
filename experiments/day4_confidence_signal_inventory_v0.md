# Day 4 Inference-Time Confidence Signal Inventory v0

## Scope

This inventory examines signals available to the frozen BM25 plus reasoning pipeline without
using `development_calibration` labels or locked-test data. It selects no threshold and makes no
performance claim.

## Inventory

| Signal | Available at inference time? | Present in current artifacts? | Decision for first local feature pass |
|---|---:|---:|---|
| BM25 top-1 raw score | yes | no; only page order was retained | add to a new immutable feature artifact |
| BM25 top-1 minus top-2 margin | yes | no | add; observed semantic and ambiguous-ranking failures motivate it |
| BM25 top-1 minus top-3 margin | yes | no | add as a descriptive companion, not a separate policy yet |
| Number of positive-score pages in the document | yes | no | add; distinguishes concentrated from zero/flat lexical matches |
| Query token count and unique-token count | yes | no | add for score interpretation; do not treat length alone as confidence |
| Extraction status of retrieved Top-3 pages | yes | available in Page Records, absent from BM25 result | add counts for normal, low-text, and missing-text pages |
| Top-K page count | yes | yes | drop as a confidence signal because Top-3 is fixed and therefore constant |
| Answer versus abstention status | yes, after generation | yes | retain as the policy action, not as a scalar confidence score |
| Citation is within supplied context | yes, after generation | yes | retain as a hard validity check; current smoke results do not show score separation |
| Number of cited supplied pages | yes, after generation | yes | diagnostic only; naive “cite every supplied page” is invalid when retrieval includes distractors |
| Repeated-run answer agreement | yes | no | defer because it multiplies paid calls |
| Separate answerability predictor | yes in principle | no | defer; it adds another model/component without evidence yet |
| Sparse/dense agreement | yes in principle | no dense baseline yet | defer until the mandatory dense baseline exists |
| Model token log-probability | provider-dependent | unavailable in the current runner | do not use in v0 |

## Forbidden policy features

The following are available only during evaluation or Oracle analysis and must never enter an
inference-time confidence score or threshold:

- benchmark `answer.is_answerable`;
- gold evidence pages, gold-page coverage, recall, or complete-evidence labels;
- gold bbox, facts, answer text, evidence type, evidence-page count, or extract class;
- Oracle condition identity;
- manual `evidence_sufficient`, answer-correctness, or grounding-correctness labels;
- locked-test outcomes.

These fields may be used only as targets, audit labels, or reporting slices under the frozen
protocol.

## Current artifact gap

`data/derived/bm25_page_v0_tune_results.json` is a valid immutable retrieval-evaluation artifact,
but it stores only ranked page IDs and gold-derived evaluation scores. It does not retain the raw
BM25 scores needed for inference-time confidence analysis. It must not be overwritten.

The next artifact will therefore rerun the same frozen BM25 configuration on
`development_tune` and store a separate, answer-free feature record for all 256 tune questions,
including the 17 benchmark-unanswerable questions. The feature generator may read only question
text, document identity, Page Records, and frozen BM25 configuration. Answerability and gold
evidence annotations are excluded from its output and from feature computation.

## Frozen first-pass feature set

The first local feature pass is limited to:

1. `bm25_top1_score`;
2. `bm25_top2_score`;
3. `bm25_top3_score`;
4. `bm25_top1_top2_margin`;
5. `bm25_top1_top3_margin`;
6. `bm25_positive_page_count`;
7. `query_token_count` and `query_unique_token_count`;
8. Top-3 extraction-status counts.

No feature weights, combined confidence formula, or abstention threshold are selected at this
stage. Feature usefulness must first be evaluated against answer/grounding outcomes on
`development_tune`; thresholds remain calibration-only.
