# Dense Tune Run: 256 Tokens, 64-Token Overlap

**Date:** 2026-09-08  
**Split:** `development_tune` only  
**Paid API cost:** USD 0

## Question

Does retaining 64 tokens across adjacent 256-token chunk boundaries recover
enough evidence to justify its additional computation and storage?

## Result

At K=10, 64-token overlap achieved 92.89% Any-Evidence Recall and 73.22%
Complete-Evidence Recall, compared with 93.72% and 74.06% for zero overlap.
MRR also decreased from 0.6810 to 0.6749.

At the query level, overlap gained two and lost four Any-Evidence successes. It
gained three and lost five Complete-Evidence successes. The representation grew
from 8,217 to 10,334 chunks; summed index-build time increased from 151.17 to
185.83 seconds; embedding storage increased from 24.07 to 30.28 MiB.

## Decision

Do not prefer 64-token overlap for the 256-token configuration. The added
computation did not improve the primary macro retrieval metrics. Continue the
two predeclared 512-token runs before selecting and freezing the Dense baseline.
No calibration labels or locked-test content were accessed.
