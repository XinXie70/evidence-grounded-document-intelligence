# Day 5 R2 Retrieval Evaluation v0

## Scope

- Split: `development_tune`
- R2 trigger: entire document has zero native-text pages
- Documents: 2
- OCR pages: 88
- Eligible questions: 9
- Exclusions: 0
- Paid API cost: `$0`

Candidate configuration:

- deterministic Tesseract OCR;
- BM25 with first-occurrence query-token deduplication;
- `k1=1.2`, `b=0.75`;
- Top-10 page retrieval.

Gold evidence pages were read only after each label-free ranking was produced.

## Aggregate results

| K | Any evidence recall | Complete evidence recall | Macro page recall |
|---:|---:|---:|---:|
| 1 | 44.44% | 22.22% | 33.33% |
| 3 | 44.44% | 33.33% | 38.89% |
| 5 | 55.56% | 33.33% | 44.44% |
| 10 | 88.89% | 55.56% | 72.22% |

At Top-10, 8 of 9 questions retrieved at least one gold page, while only 5 of 9
retrieved every required page. Therefore the candidate is not ready for batch
grounded-reasoning calls across all R2 questions.

## Per-question Top-10 evidence completeness

| Document | Question | Gold pages | Gold pages found | Complete |
|---|---|---|---|---|
| groundwater | q1 | 10, 11 | 10, 11 | yes |
| groundwater | q2 | 10, 11, 12 | 10, 11 | no |
| groundwater | q3 | 12, 13 | 13 | no |
| groundwater | q4 | 12, 13, 19 | 19 | no |
| groundwater | q5 | 10, 11 | 10, 11 | yes |
| bird program | q1 | 14 | none | no |
| bird program | q2 | 9 | 9 | yes |
| bird program | q3 | 12 | 12 | yes |
| bird program | q5 | 8, 9 | 8, 9 | yes |

## Failure interpretation

Three incomplete cases expose a local page-boundary problem:

- groundwater q2 retrieved pages 10 and 11 but missed adjacent page 12;
- groundwater q3 retrieved page 13 but missed adjacent page 12; and
- bird-program q1 retrieved page 13 at rank 4 while the required table is on
  adjacent page 14.

Groundwater q4 is a harder document-level composition case spanning laboratory
tables on pages 12 and 13 and a site map on page 19. It retrieved page 19 only and
cannot be repaired solely by expanding around that page.

## Decision

Do not send all nine questions to the reasoning API. Retain the current R2
configuration as a candidate and next evaluate a deterministic, label-free adjacent
page expansion over the retrieved candidate pool. Treat groundwater q4 separately as
a mixed table-to-map composition failure.
