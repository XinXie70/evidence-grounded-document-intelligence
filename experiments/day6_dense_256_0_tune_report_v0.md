# Dense Tune Run: 256 Tokens, No Overlap

**Date:** 2026-09-08  
**Split:** `development_tune` only  
**Paid API cost:** USD 0

## Configuration

The pinned `BAAI/bge-small-en-v1.5` revision was run on CPU. Text was split
within physical-page boundaries into model inputs of at most 256 tokens,
including special tokens, with zero overlap. Maximum chunk similarity was used
as the physical-page score.

## Result

The frozen denominator contained 239 eligible questions; 17 questions were
excluded by the existing protocol. At K=10, Dense achieved 93.72% Any-Evidence
Recall and 74.06% Complete-Evidence Recall. The frozen page-level BM25 baseline
achieved 89.54% and 70.71%, respectively, on the same questions.

Dense also improved MRR from 0.6119 to 0.6810 and nDCG@10 from 0.6258 to
0.6799. It built 8,217 chunk embeddings across 81 evaluated documents, using
24.07 MiB for the float embeddings. Summed CPU index-build time was 151.17
seconds; mean query time was 13.58 milliseconds.

## Complementarity

At Any-Evidence Recall@10, Dense alone succeeded on 16 questions and BM25 alone
succeeded on 6. At Complete-Evidence Recall@10, Dense alone succeeded on 26
questions and BM25 alone succeeded on 18. This is an early complementarity
signal, not yet a decision to adopt hybrid retrieval.

## Decision

Continue the four-point predeclared Dense grid. Do not select a configuration
or implement hybrid fusion until all four configurations are compared. No
calibration labels or locked-test content were accessed.
