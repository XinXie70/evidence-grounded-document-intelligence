# BM25–Dense Complementarity Audit

**Date:** 2026-09-08  
**Split:** `development_tune` only  
**Questions:** 239 evidence-retrieval-eligible questions  
**Paid API cost:** USD 0

## Purpose

This audit tests the preregistered hybrid gate: a hybrid experiment is allowed
only if the frozen BM25 and Dense baselines demonstrate query-level
complementarity. Both runs were paired by question ID and checked for identical
questions, documents, gold pages, slices, and split.

## Paired Result at K=10

| Outcome | Any evidence | Complete evidence |
|---|---:|---:|
| Both succeed | 208 | 151 |
| BM25 only | 6 | 18 |
| Dense only | 16 | 26 |
| Neither | 9 | 44 |

The two Top-10 lists have a mean union size of 14.56 unique pages. As an
unranked candidate-pool ceiling, this union reaches 96.23% Any-Evidence Recall
and 82.43% Complete-Evidence Recall. This is not a deployable Top-10 hybrid
score: it uses up to 20 pages and therefore only measures whether useful
complementary candidates exist.

## Failure Pattern

Dense uniquely completes the evidence for 26 questions, including ten table
questions. BM25 uniquely completes 18 questions. Both unique-success groups
are dominated by multi-page questions: 20 of 26 for Dense and 17 of 18 for
BM25. Of the 44 questions completed by neither method, 42 require multiple
pages, 22 use mixed evidence, and six have missing gold-page text layers.

This supports two distinct conclusions. First, semantic retrieval adds real
coverage rather than merely reproducing BM25. Second, multi-page evidence
assembly remains the main text-retrieval bottleneck; rank fusion cannot repair
pages whose usable text is absent.

## Decision

The protocol gate for a minimal hybrid experiment is satisfied. Predeclare one
deterministic rank-fusion ablation on `development_tune`. Reciprocal Rank Fusion
is the appropriate first candidate because the persisted baseline artifacts
provide comparable ranks rather than calibrated cross-system score units. The
hybrid is not adopted unless its fixed Top-K metrics improve over the frozen
BM25 and Dense baselines. Calibration and locked test remain untouched.
