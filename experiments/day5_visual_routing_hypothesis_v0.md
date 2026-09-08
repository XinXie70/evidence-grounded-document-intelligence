# Day 5 Visual Routing Hypothesis v0

## Purpose

Convert the observed Day 5 failures into a small, testable routing hypothesis. The router must not
use benchmark answers, gold evidence pages, or answerability labels at inference time.

## Observable inputs allowed

- the user question;
- document-level native-text coverage;
- page-level native-text quality;
- BM25 rankings and scores;
- PDF page images.

## Proposed routes

### R0 - ordinary text route

Use native page text and BM25 when the document has usable text and the question does not require
visual layout or exhaustive document-wide inspection.

This remains the default because it is cheaper, faster, searchable, and already succeeds on many
questions.

### R1 - local visual fallback

When the question explicitly refers to a chart, figure, diagram, or other two-dimensional visual
relationship, render the BM25 top-K candidate pages and provide their images to the reasoning
model.

Observed support: `pilot_06`. BM25 ranked the correct page 30 at rank 2, but linearized text mapped
the question to the wrong percentage. The image recovered the correct answer.

### R2 - scanned-document fallback

When document-level native-text coverage is effectively zero, do not treat BM25's page ordering as
meaningful. The system requires a separate page-image discovery step before answer generation.

Observed support:

- `pilot_16`: 37/37 pages empty, 0 extracted characters;
- `pilot_17`: 51/51 pages empty, 0 extracted characters.

Sending images of BM25 pages 1, 2, and 3 would not recover these cases because the correct evidence
is on pages 10-11 and 12. Day 5 proves that visual reasoning works after the correct regions are
supplied; it does not yet solve visual page discovery.

### R3 - document-global route

When a question asks for an exhaustive property across the entire document, a top-K evidence input
cannot prove that omitted pages contain no additional instances. The system must either inspect the
complete document under a bounded design or abstain.

Observed support: `pilot_18`. The phrase "across the entire document" required negative coverage of
all 42 pages. Supplying only six benchmark-positive pages was insufficient for a valid global count.

## Current decision boundary

This artifact defines hypotheses, not a finished router:

- R0 and R1 are ready for a small deterministic smoke test.
- R2 requires a bounded page-image discovery experiment; do not pretend BM25 can retrieve empty
  pages.
- R3 remains an explicit abstention condition until a document-complete experiment is designed.

## Next test

Implement only the label-free question and document signals needed to assign R0-R3, then test them
against hand-constructed examples and the four already-audited Day 5 cases. No paid model call is
needed for that test.
