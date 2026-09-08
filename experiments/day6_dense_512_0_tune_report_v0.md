# Dense Tune Run: 512 Tokens, No Overlap

**Date:** 2026-09-08  
**Split:** `development_tune` only  
**Paid API cost:** USD 0

## Question

Does doubling the maximum chunk length from 256 to 512 model-input tokens
provide enough additional context to improve evidence-page retrieval?

## Result

At K=10, the 512-token condition achieved 92.47% Any-Evidence Recall and
72.38% Complete-Evidence Recall, compared with 93.72% and 74.06% for the
256-token zero-overlap condition. MRR decreased from 0.6810 to 0.6741 and
nDCG@10 decreased from 0.6799 to 0.6687. Top-1 Any-Evidence Recall increased
slightly, from 54.81% to 55.23%, but this did not persist at the primary K=10
comparison.

At the question level, the 512-token condition gained two and lost five
Any-Evidence successes at K=10. It gained five and lost nine Complete-Evidence
successes.

Longer chunks reduced the representation from 8,217 to 5,129 chunks and the
embedding storage from 24.07 to 15.03 MiB. However, summed CPU index-build time
increased from 151.17 to 225.33 seconds because each individual sequence was
longer. Mean query time was 15.11 milliseconds.

## Decision

Do not prefer 512 tokens with zero overlap over the current 256-token
zero-overlap candidate. Its primary K=10 retrieval metrics were weaker despite
its smaller stored representation. Complete the final predeclared 512-token,
64-token-overlap run before freezing the Dense baseline. No calibration labels
or locked-test content were accessed.
