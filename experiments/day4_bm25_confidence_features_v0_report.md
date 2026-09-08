# Day 4 BM25 Confidence Feature Artifact v0

## Purpose

This artifact records inference-time signals from the frozen BM25 page retriever before any
confidence formula or abstention threshold is chosen. It is descriptive only: a high BM25 score
is not assumed to mean a correct answer, and a low score is not assumed to mean a failure.

## Scope and leakage guard

- split: `development_tune` only;
- questions: 256, including benchmark-answerable and benchmark-unanswerable questions;
- source inputs: question text, document identity, verified Page Records, and frozen BM25 config;
- excluded from every feature record: question text, benchmark answer, answerability label, gold
  evidence pages, facts, bboxes, extract class, and all manual outcome labels;
- locked test and `development_calibration` were not used.

The resulting immutable artifact is
`data/derived/bm25_page_v0_tune_confidence_features.json` with SHA-256:

`f8969c5cbbd074641d59be009638342b06f69f9cd7fbf1051dbec99fd234de74`

An independent repeat generation produced the same SHA-256 and was byte-for-byte identical.

## Recorded signals per question

- BM25 top-1, top-2, and top-3 scores;
- top-1 minus top-2 and top-1 minus top-3 score margins;
- number of document pages with a positive BM25 score;
- query token count and unique-token count;
- retrieved Top-3 page IDs;
- counts of `ok`, `low_text`, and `text_layer_missing` pages among the Top-3.

These are all available when the system is answering a new question. None tells the system the
correct answer or correct evidence page.

## Descriptive audit

| Signal | Minimum | Median | Maximum |
|---|---:|---:|---:|
| BM25 top-1 score | 0.000 | 21.162 | 82.791 |
| BM25 top-1 minus top-2 margin | 0.000 | 2.344 | 32.541 |
| Positive-score page count | 0 | 40 | 92 |

Additional counts:

- 9 / 256 questions have a top-1 score of zero;
- 13 / 256 questions have a zero top-1/top-2 margin;
- 9 / 256 questions retrieve at least one non-`ok` text-layer page in the Top-3.

These counts identify cases worth auditing. They are not failure counts and must not yet be used
as abstention rules.

## Verification

- byte-for-byte deterministic rerun: passed;
- forbidden answer/gold keys absent: passed;
- full local test suite: 83 tests passed;
- no paid API request was required for feature generation or verification.

## Next decision gate

The next step is to pair these label-free signals with independently audited grounded-reasoning
outcomes on `development_tune`. We will ask whether particular signals are actually associated
with incorrect answers, incomplete grounding, or justified abstention. Only after observing that
relationship may we propose a confidence rule; any numeric abstention threshold must still be
selected on `development_calibration`, not on tune or locked test.
