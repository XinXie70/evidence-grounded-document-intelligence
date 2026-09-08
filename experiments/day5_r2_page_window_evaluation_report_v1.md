# R2 Bounded Page-Window Ablation v1

## Question

Can the R2 scanned-document candidate set be compressed to at most nine pages
without losing the evidence coverage recovered by adjacent-page expansion?

## Frozen comparison

All methods use the same two tune-split R2 documents, nine answerable questions,
Tesseract OCR corpus, BM25 parameters, and deduplicated query tokens. Gold evidence
pages are read only after each candidate list has been selected.

| Candidate method | Mean pages | Any evidence | Complete evidence | Macro page recall |
|---|---:|---:|---:|---:|
| BM25 Top-10 | 10.00 | 8/9 (88.89%) | 5/9 (55.56%) | 72.22% |
| Adjacent expansion around Top-10 | 16.78 | 9/9 (100.00%) | 8/9 (88.89%) | 92.59% |
| Sliding three-page windows v0 | 9.00 | 8/9 (88.89%) | 6/9 (66.67%) | 75.93% |
| BM25-anchor-centered windows v1 | 9.00 | 8/9 (88.89%) | 7/9 (77.78%) | 81.48% |

## What v1 fixed

For groundwater q3, BM25 ranked physical page 13 but the gold evidence spans
pages 12 and 13. Centering a three-page window on page 13 selected pages 12--14,
recovering complete evidence where the sliding-window v0 selected pages 13--15.

## Remaining failures

- Groundwater q4 still retrieves physical page 19 but misses gold pages 12 and 13.
- Bird-registration q1 still misses physical page 14. Its relevant centered window
  (pages 12--14) scores 23.94, while three irrelevant or incomplete windows score
  above 32 and consume the nine-page allowance.

The second failure shows that globally optimizing the same BM25 window-sum
objective would not change the selected windows. The bottleneck is the weak OCR /
lexical score assigned to the relevant visual table region, not merely greedy
window selection.

## Decision

Do not promote the nine-page window method as the R2 default. Retain adjacent-page
expansion as the higher-recall candidate generator for now. Treat bounded windows
as a documented compression ablation: they reduce context size, but the observed
11.11 percentage-point loss in complete evidence recall is too large.

The next experiment should separate high-recall candidate generation from
reasoning-context compression instead of asking one BM25 score to perform both
jobs.
