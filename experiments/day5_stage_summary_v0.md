# Day 5 Stage Summary v0

## Where the project is now

The project has moved beyond the initial BM25 baseline and has completed a
failure-driven R2 scanned-document candidate on `development_tune`. It has not
completed every routing path, calibration, or the locked final test.

The implemented system boundary is:

1. route each question and document using observable, label-free signals;
2. retrieve physical evidence pages;
3. preserve page identity and layout-bearing text in the reasoning context;
4. let the answer model answer or abstain using only supplied evidence;
5. validate citations and retain cost, token, latency, configuration, and input
   hashes.

## Current routing workflow

```text
Question + PDF
      |
      v
Deterministic router
      |
      +-- R0: usable native text, ordinary question
      |       -> native Page Records -> BM25
      |
      +-- R1: explicit chart / figure / diagram / map / table signal
      |       -> retrieve candidate pages -> bounded visual evidence fallback
      |
      +-- R2: zero usable native-text pages
      |       -> full-document local OCR
      |       -> retry page orientation only when OCR confidence < 40
      |       -> page BM25 with deduplicated query tokens
      |       -> three centered three-page windows
      |       -> for an explicit em-dash multi-hop question, add at most one
      |          fully novel clause-derived window
      |       -> 9 to 12 layout-preserved OCR pages -> grounded reasoning
      |
      +-- R3: explicit whole-document / all-pages requirement
              -> document-complete processing required, otherwise abstain
```

The router, guarded R2 OCR preparation, page ranking, orientation selection,
window selection, reasoning call, structured output validation, and cost logging
are implemented. R1 remains a bounded fallback supported by controlled visual
diagnostics rather than a completed population-level visual retrieval pipeline.
R3 remains a deliberate abstention or document-complete-processing boundary.

## Failure-driven R2 development chain

### 1. Missing native text

Two scanned documents had zero usable native-text pages. Native BM25 therefore
returned meaningless page-number tie order. Full-document Tesseract OCR restored
searchable page text without using benchmark labels.

### 2. Flattened OCR layout

Flattened OCR made a five-item list appear to contain four items. Passing the same
OCR with line structure preserved changed the reasoning answer from 4 to the
correct 5. This justified layout-preserved OCR context.

### 3. Multi-page evidence

Query-token deduplication brought both groundwater measurement pages into Top-10.
The unchanged reasoning model then calculated the correct 1.05-foot difference
and cited both pages.

### 4. Upside-down evidence page

Bird-registration page 14 was retrieved only after adjacent expansion, but its
baseline OCR was upside down. Among 57 unique R2 candidate pages it had the lowest
original-orientation mean OCR confidence, 35.73; the next lowest was 48.25.

A frozen `< 40` trigger selected only that page. Four-way cardinal OCR selected
180 degrees by confidence mass, restored `Bloodline/ Relation Information` and
`Example: (father of #11 and #12)`, and moved page 14 from outside BM25 Top-10 to
rank 1. The other eight question rankings were unchanged.

### 5. Bounded context windows

After orientation recovery, three centered three-page windows matched adjacent
expansion at 8/9 complete-evidence questions while reducing mean candidate pages
from 16.44 to 9.

### 6. Explicit multi-hop retrieval

The remaining groundwater question contained an explicit em dash between a
laboratory-table comparison and a site-map lookup. Retaining the full-query
windows and adding one fully non-overlapping clause-derived window recovered
pages 12, 13, and 19.

On the nine-question R2 tune inventory, the resulting candidate achieved:

- any-evidence recall: 9/9;
- complete-evidence recall: 9/9;
- macro page recall: 100%;
- mean reasoning pages: 9.33;
- maximum reasoning pages: 12.

These are tune results, not held-out performance claims.

### 7. End-to-end causal check

One paid, zero-retry q4 request used the frozen 12-page context. The model
identified MW3, answered `Davis Street`, and cited exactly pages 12, 13, and 19,
matching the benchmark evidence chain. Actual estimated cost was USD 0.015781.

This establishes that the earlier q4 failure was retrieval-associated. Once the
complete evidence was supplied, the unchanged reasoning model completed the
table-to-map chain.

## Route status at freeze

| Route | Current status | What is supported | What remains |
|---|---|---|---|
| R0 native text | baseline implemented | deterministic Page Records and BM25 | broader candidate comparison and final evaluation |
| R1 local visual | diagnostic support | visual recovery for chart/layout failures when correct pages are available | automated candidate-image evaluation at scale |
| R2 scanned document | tune candidate v2 frozen | OCR, orientation recovery, bounded retrieval, multi-hop supplement, grounded smoke | unchanged validation on unseen documents |
| R3 document global | safe boundary implemented | detects explicit whole-document requirements and avoids unsupported top-K claims | bounded document-complete design or continued abstention |

## Data boundary and next gate

- `development_tune`: 256 questions across 82 documents; permitted for the work
  summarized above.
- `development_calibration`: 132 questions across 35 document-disjoint documents;
  not used to choose this R2 architecture or its thresholds.
- locked official test: 730 questions across 156 documents; not authorized for
  modelling access. The access guard remains active.

The next permitted step is a calibration preflight, not the locked test. Before
any calibration run, determine the R0--R3 composition without using answer or
evidence labels, verify that required PDF/OCR inputs are available, declare the
metrics and failure policy, and write a cost estimate. R2 v2 must remain unchanged
during that validation.
