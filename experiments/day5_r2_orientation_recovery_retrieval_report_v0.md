# R2 Orientation Recovery and Retrieval Report v0

## Controlled intervention

Only bird-registration physical page 14 changed. The original 51-page OCR corpus
was copied to a derived corpus, and page 14 was replaced with the 180-degree OCR
selected by label-free Tesseract confidence. The groundwater corpus, BM25
parameters, query-token policy, questions, and tune split remained unchanged.

## Page-level retrieval effect

Across all nine R2 questions, only bird-registration q1 changed ranking:

- Before recovery, gold physical page 14 was outside BM25 Top-10.
- After recovery, physical page 14 ranked first.
- The other eight questions retained identical Top-10 rankings.

| Method | Mean candidate pages | Any evidence | Complete evidence | Macro page recall |
|---|---:|---:|---:|---:|
| Original OCR, BM25 Top-10 | 10.00 | 8/9 (88.89%) | 5/9 (55.56%) | 72.22% |
| Recovered OCR, BM25 Top-10 | 10.00 | 9/9 (100.00%) | 6/9 (66.67%) | 83.33% |
| Recovered OCR, adjacent expansion | 16.44 | 9/9 (100.00%) | 8/9 (88.89%) | 92.59% |
| Recovered OCR, three centered windows | **9.00** | **9/9 (100.00%)** | **8/9 (88.89%)** | **92.59%** |

The centered-window method now matches adjacent expansion while using 45.27%
fewer candidate pages on average.

## Causal interpretation

Before orientation recovery, the centered-window method missed bird physical page
14 because its upside-down OCR received a weak lexical score. After the upstream
representation error was repaired, page 14 became rank 1 and its centered window
selected pages 13--15. The earlier compression failure was therefore downstream
of OCR orientation, not evidence that bounded windows were inherently inadequate.

## Remaining failure

Groundwater q4 requires a multi-hop chain:

1. compare gasoline concentrations across laboratory tables on pages 12 and 13;
2. identify the relevant monitoring well;
3. locate that well on the site map on page 19 and determine the nearest street.

The candidate retrieves page 19 but misses pages 12 and 13. This is the sole
incomplete-evidence case. It should drive the next retrieval experiment; no change
to the reasoning model is justified yet.

## Decision

Freeze the combined pipeline as R2 tune candidate v1, not as a final or held-out
result. Its orientation threshold and retrieval choices were selected on tune data
and must remain unchanged during later held-out validation.
