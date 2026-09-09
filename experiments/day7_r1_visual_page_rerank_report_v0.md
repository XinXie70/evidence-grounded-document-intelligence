# R1 Visual Page Rerank Result v0

**Split:** `development_tune` only  
**Questions:** 63 frozen-router R1 questions  
**Paid API cost:** USD 0  
**Decision:** drop

## Tested intervention

Within each question's frozen BM25–Dense RRF Top-10 pool, pages compatible with the question's
visual cue were moved first. Table questions preferred pages detected as tables; chart, graph,
diagram, figure, and map questions preferred pages containing raster or vector objects. Original
RRF order was preserved within preference groups.

The reranker used no gold pages, bboxes, facts, answers, calibration data, or locked-test data.
Gold pages were read only after rankings were frozen for deterministic scoring.

## Aggregate comparison

| Cutoff | Metric | Original RRF | Visual rerank | Delta |
|---:|---|---:|---:|---:|
| 1 | Any evidence | 33/63 | 33/63 | 0 |
| 1 | Complete evidence | 16/63 | 17/63 | +1 |
| 3 | Any evidence | 50/63 | 51/63 | +1 |
| 3 | Complete evidence | 35/63 | 35/63 | 0 |
| 5 | Any evidence | 57/63 | 58/63 | +1 |
| 5 | Complete evidence | 44/63 | 44/63 | 0 |
| 10 | Any evidence | 60/63 | 60/63 | 0 |
| 10 | Complete evidence | 55/63 | 55/63 | 0 |

At both primary compression cutoffs, the rule exchanged rather than eliminated errors:

- Top-3: two complete-evidence gains and two complete-evidence losses;
- Top-5: two complete-evidence gains and two complete-evidence losses.

## Why the hypothesis failed

The binary layout signal was insufficiently discriminative inside already-relevant RRF pools.
All ten candidates were marked visually compatible for every `bar chart` and `diagram` question.
Eight of eleven `chart` questions also marked all ten pages compatible. Across chart-family cues,
an average of roughly 9–10 of ten candidates contained raster or vector objects.

Table detection was less saturated but still coarse: the 42 table questions averaged 5.48
preferred pages in their Top-10 pools. Detecting that a page contains some table does not establish
that the table matches the entities, metric, period, or comparison requested by the question.

## Decision and final-evaluation consequence

Drop this reranker under the preregistered keep/drop rule because Complete Evidence Recall@3 and
@5 did not improve. Preserve original RRF ordering and do not compress R1 to Top-2 or Top-3 using
these signals.

This was the single bounded tune-only R1 iteration allowed by the final-evaluation gate. The
portfolio MVP therefore closes without calibration or locked-test claims. A future research
version would require a separately scoped question-conditioned visual localizer, not another
post-hoc weight change to this binary rule.

## Reproducibility

- Result: `day7_r1_visual_page_rerank_result_v0.json`
- Result SHA-256: `943f2ef2b117869400365ac0ab64e070f5b7d76aa116912837b950a376ea8689`
- Automated tests after implementation: 291 passed
