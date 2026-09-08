# Dense Tune Run: 512 Tokens, 64-Token Overlap

**Date:** 2026-09-08  
**Split:** `development_tune` only  
**Paid API cost:** USD 0

## Question

Can a 64-token overlap recover evidence lost by the 512-token, zero-overlap
condition and justify a more complex chunking rule?

## Result

At K=10, this condition achieved 92.47% Any-Evidence Recall and 74.06%
Complete-Evidence Recall. The overlap recovered Complete-Evidence Recall from
the 72.38% observed for 512/0, but did not improve on the 74.06% achieved by
256/0. Any-Evidence Recall, MRR, and nDCG@10 remained below 256/0.

Compared question by question with 256/0, each condition uniquely completed
all gold evidence pages for seven questions. For Any-Evidence Recall, 256/0
uniquely succeeded on five questions while 512/64 uniquely succeeded on two.

This condition produced 5,602 chunks and 16.41 MiB of embeddings. Summed CPU
index-build time was 253.08 seconds. Timing is reported for reproducibility but
is not treated as a precise benchmark because the runs were not performed in a
controlled performance environment.

## Decision

Do not select 512/64. Freeze 256/0 as the B2 Dense baseline because it ties the
best primary Complete-Evidence Recall@10, leads the other primary ranking and
retrieval metrics, and uses the simpler zero-overlap rule. No calibration labels
or locked-test content were accessed.
