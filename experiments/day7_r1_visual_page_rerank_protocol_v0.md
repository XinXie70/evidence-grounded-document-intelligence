# R1 Visual Page Rerank Protocol v0

**Split:** `development_tune` only  
**Eligible questions:** 63 questions selected by frozen visual router v1  
**Paid API budget:** USD 0 for this retrieval experiment  
**Status:** predeclared before implementation and scoring

## Observed problem

The frozen RRF Top-10 candidate pool has high but imperfect evidence coverage for R1 questions.
Sending only the first few pages to a visual reasoner would discard required evidence; sending ten
full-resolution page images increases cost and distraction.

| RRF cutoff | Any evidence | Complete evidence |
|---:|---:|---:|
| 1 | 33/63 | 16/63 |
| 3 | 50/63 | 35/63 |
| 5 | 57/63 | 44/63 |
| 10 | 60/63 | 55/63 |

## Hypothesis

For questions explicitly mentioning a table, chart, figure, graph, image, diagram, or map, PDF
layout signals available without benchmark labels can prioritize visually structured pages within
the RRF Top-10 pool.

## Frozen candidate design

1. Candidate pool remains the frozen equal-weight BM25–Dense RRF Top-10.
2. Extract only PDF-native observable page signals: image count, detected table count, and vector
   object counts (lines, rectangles, and curves).
3. Use the router's matched visual term to choose a fixed page-type preference:
   - `table` prefers detected-table pages;
   - `chart`, `graph`, `diagram`, `figure`, and `map` prefer pages with images or vector objects;
   - `image` and `illustration` prefer pages containing raster images.
4. Preserve RRF order within equal preference groups.
5. Never use gold pages, bboxes, answers, facts, or calibration records at runtime.

## Primary evaluation

- Complete Evidence Recall@3 and @5 within the same 63-question R1 tune set.
- Any Evidence Recall@3 and @5 as secondary metrics.
- Report Top-10 candidate ceiling unchanged by construction.
- Report gains and losses relative to original RRF per question, especially multi-page cases.

## Keep/drop rule

Keep the visual rerank only if Complete Evidence Recall improves at either K=3 or K=5 without a
material loss at the other cutoff. Do not select a Top-2 package. If the rule fails, retain RRF
order and treat the ten-page budget as the unresolved R1 trade-off.

This is the single bounded tune-only R1 iteration allowed by the final-evaluation gate.
