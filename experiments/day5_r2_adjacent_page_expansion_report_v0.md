# Day 5 R2 Adjacent-Page Expansion Evaluation v0

## Purpose

Test whether the incomplete R2 Top-10 results are caused by page-boundary effects.
This ablation expands each BM25 seed page with its immediate previous and next
physical pages. The rule is deterministic, document-bounded, and label-free.

This is candidate generation only. Expanded pages are not automatically sent to a
reasoning model.

## Configuration

- Input: R2 deduplicated-query BM25 Top-10
- Expansion radius: 1 physical page
- Per-seed order: seed, previous page, next page
- Out-of-document pages: dropped
- Duplicates: removed at first occurrence
- Split: `development_tune`
- Questions: 9
- Paid API cost: `$0`

## Results

| Metric | BM25 Top-10 | Expanded candidate pool | Change |
|---|---:|---:|---:|
| Any evidence recall | 88.89% (8/9) | 100.00% (9/9) | +11.11 pp |
| Complete evidence recall | 55.56% (5/9) | 88.89% (8/9) | +33.33 pp |
| Macro page recall | 72.22% | 92.59% | +20.37 pp |

Expanded candidate-pool size:

- minimum: 12 pages;
- maximum: 24 pages; and
- mean: 16.78 pages.

## Recovered cases

- Groundwater q2 recovered missing page 12 from adjacent pages 10 and 11.
- Groundwater q3 recovered missing page 12 from retrieved page 13.
- Bird-program q1 recovered gold page 14 from retrieved page 13.

## Remaining failure

Groundwater q4 still retrieves only gold page 19 and misses gold pages 12 and 13.
The question composes laboratory-analysis tables with a site-vicinity map, so local
adjacency around page 19 cannot recover the distant table evidence.

## Decision

Adjacent expansion is effective as a recall-oriented candidate-generation stage, but
the 12-to-24-page pool is too large to adopt directly as grounded-reasoning context.
The next experiment should score short contiguous page windows and select a bounded
number of high-scoring windows. This tests whether multi-page table regions can be
retained while returning the final context to a controlled page budget.
