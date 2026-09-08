# Day 4 BM25 Confidence-Signal Smoke Audit v0

## Question

Can inference-time BM25 signals distinguish sufficient retrieval from retrieval-associated
evidence loss in the already completed ten-case C1 Real Retrieval smoke set?

This is a stratified diagnostic sample, not a random sample and not a performance estimate. No
threshold is selected here.

## Paired audit

| Case | Top-1 score | Top-1 − Top-2 | Positive pages | Top-3 text status | Audited C1 outcome |
|---|---:|---:|---:|---|---|
| 01 | 11.917 | 0.197 | 53 | 3 ok | grounded answer success |
| 02 | 37.265 | 1.092 | 92 | 3 ok | grounded answer success |
| 03 | 22.056 | 0.004 | 40 | 3 ok | appropriate abstention; required page missing |
| 04 | 12.679 | 0.152 | 66 | 3 ok | appropriate abstention; semantic evidence missing |
| 05 | 23.023 | 4.903 | 32 | 3 ok | grounded answer success |
| 06 | 37.202 | 3.234 | 60 | 3 ok | appropriate abstention; exact facts missing |
| 07 | 29.706 | 13.350 | 34 | 3 ok | grounded answer success |
| 08 | 11.186 | 0.055 | 44 | 3 ok | appropriate abstention; all gold pages missing |
| 09 | 0.000 | 0.000 | 0 | 3 text-layer missing | appropriate abstention; scanned evidence unavailable |
| 10 | 26.003 | 3.763 | 34 | 3 ok | correct abstention on benchmark-unanswerable question |

## What is supported

1. Case 09 is detectable by a zero BM25 score, zero positive pages, and missing text layers.
2. Cases 03, 04, and 08 combine retrieval-associated evidence loss with very small Top-1/Top-2
   margins.
3. A small margin is not sufficient to declare failure: case 01 succeeds with a margin of only
   0.197.
4. A high Top-1 score or moderate margin is not sufficient to declare evidence adequacy: case 06
   has a Top-1 score of 37.202 and margin of 3.234 but still lacks the two exact required facts.
5. The number of positive-score pages does not visibly separate success from failure in this tiny
   sample.
6. Case 10 shows that retrieval confidence and answerability are different questions. BM25 can
   return plausible related pages for a benchmark-unanswerable question; the reasoning system
   must still abstain.

## Decision

Do not use a single raw BM25 score or a single score-margin cutoff as the reliability policy.
The signals are useful diagnostics, but this ten-case sample does not justify weights, a combined
confidence formula, or an abstention threshold.

The next evidence-gathering step should add C0 Closed-book to a modest `development_tune` pilot
and collect independent answer-correctness, grounding, and contextual-sufficiency outcomes. That
larger tune pilot can test whether combinations of retrieval signals and post-generation checks
are associated with failures. Numeric threshold selection remains reserved for
`development_calibration`; locked test remains unopened.
