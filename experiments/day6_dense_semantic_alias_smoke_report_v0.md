# Dense Semantic-Alias Smoke Test v0

**Date:** 2026-09-08  
**Split:** `development_tune` only  
**Paid API cost:** USD 0

## Observed failure

The question asks about a detailed `investment holdings` table, while the gold
pages 13 and 14 are headed `Schedule of Investments`. The page-level BM25
baseline did not place either gold page in its Top-10.

## Fixed smoke configuration

- dense model: `BAAI/bge-small-en-v1.5`
- revision: `baab320e3049c6c62dd63560765566dd9083985e`
- within-page chunk size: 256 model-input tokens, including special tokens
- overlap: 0 tokens
- chunk-to-page aggregation: maximum chunk score
- evaluation cutoff: Top-10 physical pages

## Result

BM25 returned pages `4, 5, 9, 24, 33, 19, 10, 12, 11, 29`; neither gold page
was present. Dense ranked gold page 13 at position 3 and gold page 14 at
position 4. Therefore BM25 had zero Any- and Complete-Evidence Recall@10 for
this question, while Dense achieved both Any- and Complete-Evidence Recall@10.

## Decision

This is the expected semantic-alias recovery and justifies proceeding to the
pre-registered dense comparison on the full `development_tune` split. It does
not establish that Dense is globally better: the sample size is one, and no
calibration or locked-test data was accessed.
