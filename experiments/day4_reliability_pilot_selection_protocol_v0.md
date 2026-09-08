# Day 4 Reliability Pilot Selection Protocol v0

## Purpose and boundary

Select a fresh, deterministic 24-question `development_tune` pilot for validating Reliability /
Selective Answering evaluation. The pilot is deliberately stratified and must not be reported as
a benchmark-wide performance estimate or used to choose final thresholds.

`development_calibration` and locked test are excluded. The ten previously inspected Day 3 smoke
questions are also excluded. No final answer text or atomic facts enter selection.

## Global constraints

- exactly 24 questions;
- exactly one question per document;
- 18 benchmark-answerable and 6 benchmark-unanswerable questions;
- all selections determined by the frozen slots and SHA-256 priority below;
- no replacement after model results are observed;
- gold-derived retrieval bands and evidence metadata are selection/audit strata only and are
  forbidden as inference-time confidence features.

## Answerable slots

BM25 Top-3 bands use the frozen page scorer:

- `complete`: complete-evidence Recall@3 = 1;
- `partial`: any-evidence Recall@3 = 1 and complete-evidence Recall@3 = 0;
- `none`: any-evidence Recall@3 = 0.

Each band contributes six questions.

### Complete band

1. text, single page, normal gold text;
2. text, multiple pages, normal gold text;
3. table, single page, normal gold text;
4. table, multiple pages, normal gold text;
5. mixed, multiple pages, normal gold text;
6. visual, single page, normal gold text.

### Partial band

1–2. text, multiple pages, normal gold text;
3–4. table, multiple pages, normal gold text;
5. mixed, multiple pages, low gold text;
6. visual, multiple pages, normal gold text.

### None band

1–2. text, multiple pages, normal gold text;
3. table, single page, normal gold text;
4. table, multiple pages, missing gold text layer;
5. mixed, single page, missing gold text layer;
6. visual, multiple pages, normal gold text.

For selection only, `visual` groups released evidence types `chart`, `figure`, `figure_title`, and
`vision_footnote`. Raw released evidence types remain in the manifest.

## Unanswerable slots

Unanswerable questions have no gold retrieval-completeness band. They are stratified only by the
label-free BM25 Top-1 score recorded before outcome inspection:

- two `low`: score <= 14.608;
- three `mid`: 14.608 < score < 28.046;
- one `high`: score >= 28.046.

The cut points are the frozen first and third quartiles of the 246 non-smoke tune feature records.
Only one high-band unanswerable candidate exists, so a two/two/two allocation is impossible.

## Deterministic priority

The selector orders candidates for each slot by ascending SHA-256 of:

`day4-reliability-pilot-v0-2026-09-04|<slot_id>|<question_id>`

A deterministic backtracking search takes the first complete assignment satisfying unique
question and document constraints. Candidate ordering, slot definitions, exclusions, and source
artifact hashes must be written to the resulting manifest.

At each search step, choose the unfilled slot with the fewest candidates remaining after the
current document exclusions; break slot ties by ascending slot ID. This minimum-remaining-values
rule is part of v0 and cannot be changed after selection.

## Decision gate after selection

Selection alone authorizes no API calls. After the manifest is generated and verified, estimate
C0/C1/C2 request counts and cost, accounting for identical empty-context request reuse on
unanswerable questions. Paid execution requires a new explicit budget approval.
