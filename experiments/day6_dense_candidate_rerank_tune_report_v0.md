# Day 6 dense candidate-reranking tune evaluation v0

## Purpose

Test whether the promising three-question Top-2 smoke result generalizes before adopting
dense candidate reranking or paying for more grounded-reasoning calls.

## Frozen evaluation

- Split: `development_tune` only.
- Questions: all 239 answerable, protocol-eligible tune questions.
- Candidate pool: the frozen RRF Top-10 physical pages.
- Reranker: the pinned BGE-small model with 256-token, zero-overlap within-page chunks and
  maximum chunk score per page.
- Evaluated output depths: 1, 2, 3, 5, and 10 pages.
- No calibration or locked-test record was accessed.
- No paid API was used.

The result artifact SHA-256 is
`b6a8924004f14ce4e4280acf7bef8b7f2666bdf98415328b9f848a0bcea8780e`.

## Aggregate results

| Reranked K | Any-Evidence Recall | Complete-Evidence Recall | MRR | nDCG |
|---:|---:|---:|---:|---:|
| 1 | 54.81% | 19.67% | 0.5481 | 0.5481 |
| 2 | 70.71% | 38.91% | 0.6276 | 0.5580 |
| 3 | 77.41% | 49.37% | 0.6499 | 0.5932 |
| 5 | 87.03% | 59.83% | 0.6727 | 0.6365 |
| 10 | 94.56% | 77.41% | 0.6826 | 0.6869 |

At K=2, complete-evidence recall was 73.26% for single-page questions but only 19.61%
for multi-page questions. Since 153 of the 239 eligible questions are multi-page, fixed
Top-2 reduction is not viable.

## Comparison with the original RRF ranking

Dense reranking changed RRF only marginally:

- K=1 Any-Evidence Recall: +0.84 percentage points; Complete unchanged.
- K=3 Any and Complete: both -0.42 percentage points.
- K=5 Any: +0.42 points; Complete: -0.84 points.
- K=10 membership and recall are unchanged by definition; MRR improved by 0.0035 while
  nDCG decreased by 0.0042.

## Decision

Reject fixed Top-2 dense page reduction as a general policy. Do not promote this reranker
over the frozen RRF ordering: its aggregate gains are negligible and inconsistent.

Retain the useful diagnostic from the smoke test: page-level candidate coverage can be
correct while the model still selects the wrong table fact. The next failure-driven direction
is compact, fine-grained evidence extraction within the high-coverage RRF candidate pool,
with safeguards for multi-page evidence and table boundaries. This direction must be tested
locally before another paid reasoning experiment.
