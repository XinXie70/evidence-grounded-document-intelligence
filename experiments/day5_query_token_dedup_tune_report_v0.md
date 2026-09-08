# Day 5 Query-Token Deduplication Tune Ablation v0

## Question

Does counting each query token at most once reduce the repeated-generic-token ranking failure
observed after full-document OCR on `pilot_16`, without changing the frozen page representation or
BM25 parameters?

## Experimental boundary

- Split: `development_tune` only; locked test remained inaccessible.
- Questions: 256 total, 239 eligible for evidence-page scoring, 17 protocol exclusions.
- Corpus: the already verified pypdf Page Records used by the Day 2 baseline. This experiment does
  not silently replace the general tune corpus with OCR text.
- Control: frozen BM25 v0, retaining repeated query tokens.
- Candidate: tokenize identically, then keep only the first occurrence of each query token while
  preserving order.
- Fixed settings: page retrieval unit, `k1=1.2`, `b=0.75`, and K values 1/3/5/10.
- Paid API cost: USD 0.

Artifacts:

- control result SHA-256: `8dd53c91a53d517065e36609d984dca8c798b4fe9cba72aaeb5fe2dd4b5793c7`;
- candidate config SHA-256: `c53283b1bd8d471a8b2e0695ec70d73e501c8b817bfb6018117128bd4cca6d71`;
- candidate result SHA-256: `c0bcd0cb32f4572466ba9ebed2473298732af580c865861f6f10d394b4e4c29a`.

## Aggregate comparison

| K | Metric | BM25 v0 | Query dedup | Delta |
|---:|---|---:|---:|---:|
| 1 | Any evidence recall | 47.70% | 48.54% | +0.84 pp |
| 1 | Complete evidence recall | 17.15% | 16.74% | -0.42 pp |
| 3 | Any evidence recall | 71.55% | 72.80% | +1.26 pp |
| 3 | Complete evidence recall | 43.10% | 43.93% | +0.84 pp |
| 5 | Any evidence recall | 77.41% | 77.82% | +0.42 pp |
| 5 | Complete evidence recall | 55.65% | 55.65% | 0.00 pp |
| 10 | Any evidence recall | 89.54% | 91.21% | +1.67 pp |
| 10 | Complete evidence recall | 70.71% | 74.06% | +3.35 pp |
| 10 | Macro evidence recall | 79.60% | 82.00% | +2.41 pp |
| 10 | MRR | 61.19% | 62.14% | +0.95 pp |
| 10 | nDCG | 62.58% | 63.64% | +1.06 pp |

## Paired question changes at K=10

| Metric | Improved | Worsened | Unchanged |
|---|---:|---:|---:|
| Any evidence recall | 5 | 1 | 233 |
| Complete evidence recall | 10 | 2 | 227 |
| Evidence recall | 12 | 3 | 224 |

The largest relevant aggregate gain is complete evidence recall at K=10. The result is not
uniform: at K=1, complete evidence recall falls slightly, and two questions lose complete evidence
coverage at K=10.

## Observed regressions

The two K=10 complete-recall regressions are both multi-page questions from the same document:

1. ethnic-Serb percentage comparison, gold pages 11 and 12: page 12 falls outside the candidate
   Top-10;
2. A/CSM expansion, gold pages 6 and 9: page 6 falls outside the candidate Top-10.

A third multi-page weekday-activity question loses one evidence page from Top-10, although it was
not complete under either condition. These cases show that repeated query terms can sometimes
provide useful emphasis rather than only noise.

## Interpretation and decision

The development-tune result supports the `pilot_16` failure hypothesis: repeated query-token
counting measurably affects lexical page ranking, and deterministic deduplication produces a net
Top-10 recall benefit. It does not justify overwriting BM25 v0 because gains are modest, some
multi-page cases regress, and the experiment uses the native-text tune corpus rather than a complete
OCR corpus.

Keep the candidate as a named, reproducible ablation. Do not promote it as the sole retriever or
evaluate it on locked test yet. The next failure-driven gate is to determine whether OCR plus this
candidate generalizes to the second fully scanned R2 document before considering broader OCR corpus
generation or a semantic retriever.

## Verification

The implementation retains the old behavior by default, exposes the candidate through an explicit
configuration field, rejects unknown policies, and preserves deterministic token order. The full
local suite passed 110 tests after the change.
