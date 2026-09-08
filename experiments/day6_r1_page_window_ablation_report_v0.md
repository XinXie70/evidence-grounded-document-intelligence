# Day 6 R1 Page-Window Ablation v0

## Outcome

Replacing BM25 Top 10 with a few contiguous windows failed because it discarded
useful but dispersed pages. Keeping Top 10 and supplementing a bounded number of
neighbours improved evidence coverage without creating new retrieval failures.

| Candidate policy | Mean pages | Maximum pages | Complete evidence |
|---|---:|---:|---:|
| Top 10 | 10.0 | 10 | 82.8% |
| Three 3-page windows replacing Top 10 | 9.0 | 9 | 68.8% |
| Four 3-page windows replacing Top 10 | 11.8 | 12 | 68.8% |
| Three 5-page windows replacing Top 10 | 14.5 | 15 | 79.7% |
| Top 10 plus neighbours of rank 1 | 11.1 | 12 | 84.4% |
| Top 10 plus neighbours of ranks 1-3 | 13.1 | 16 | 85.9% |
| Top 10 plus neighbours of ranks 1-5 | 15.5 | 20 | 87.5% |
| Top 10 plus radius-two neighbours of ranks 1-3 | 15.7 | 22 | 89.1% |

## Interpretation

The residual R1 failure is partly a continuity problem: tables and figures often
span adjacent pages. However, indiscriminate expansion can require as many as 22
page images and still leaves seven tune questions incomplete. More expansion is
therefore not automatically justified.

The next step is to inspect those seven failures for distinct observed causes,
such as two-clause multi-hop questions, chapter-wide enumeration, or
document-global wording. A separate targeted rule is preferable if it explains
the failures with fewer pages.

All candidate sets were generated without labels. Gold pages were applied only
after selection for development-tune scoring. No calibration label, locked-test
content, or paid API call was used.
