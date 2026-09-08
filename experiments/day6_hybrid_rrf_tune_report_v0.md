# BM25–Dense RRF Hybrid Tune Result

**Date:** 2026-09-08  
**Split:** `development_tune` only  
**Eligible questions:** 239  
**Paid API cost:** USD 0

## Intervention

The observed BM25–Dense complementarity justified one minimal rank-fusion
experiment. Equal-weight Reciprocal Rank Fusion combined each retriever's
Top-10 page ranking using a fixed rank constant of 60. No gold label, answer,
or evidence page was used during fusion. Identical scores were resolved by
ascending physical page ID.

## Result

| Method | Any@10 | Complete@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|
| BM25 | 89.54% | 70.71% | 0.6119 | 0.6258 |
| Dense 256/0 | 93.72% | 74.06% | **0.6810** | 0.6799 |
| **RRF Hybrid** | **94.56%** | **77.41%** | 0.6791 | **0.6911** |

Relative to Dense, RRF newly completed all evidence pages for 18 questions and
lost complete coverage for ten, producing a net gain of eight questions. Of
the 18 RRF-only complete successes, 17 were multi-page questions. Any-Evidence
Recall gained five and lost three questions relative to Dense.

The primary Complete-Evidence Recall@10 improved by 3.35 percentage points over
Dense and 6.69 points over BM25. MRR decreased slightly by 0.0019 relative to
Dense, so RRF is not uniformly better on every metric. At K=3 and K=5 its gains
over Dense were small.

## Decision

Adopt this fixed RRF configuration as the failure-driven text-retrieval
improvement at K=10. It targets the observed multi-page assembly failure while
remaining deterministic, training-free, and score-calibration-free.

This does not yet replace the evidence package sent to the reasoning model.
The C1 page budget must be selected and frozen separately because sending more
pages changes context length, latency, cost, and possible distraction. No
calibration labels or locked-test content were accessed.
