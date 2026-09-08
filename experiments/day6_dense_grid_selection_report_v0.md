# Dense Baseline Grid Selection

**Date:** 2026-09-08  
**Selection split:** `development_tune` only  
**Eligible questions:** 239  
**Paid API cost:** USD 0

## Predeclared Grid

The same pinned `BAAI/bge-small-en-v1.5` model, physical-page corpus, query
instruction, cosine similarity, maximum-chunk page aggregation, and evidence
scorer were used for all four conditions. Only chunk length and overlap changed.

| Chunk / overlap | Any@10 | Complete@10 | MRR | nDCG@10 | Chunks | Embeddings |
|---|---:|---:|---:|---:|---:|---:|
| **256 / 0** | **93.72%** | **74.06%** | **0.6810** | **0.6799** | 8,217 | 24.07 MiB |
| 256 / 64 | 92.89% | 73.22% | 0.6749 | 0.6786 | 10,334 | 30.28 MiB |
| 512 / 0 | 92.47% | 72.38% | 0.6741 | 0.6687 | 5,129 | 15.03 MiB |
| 512 / 64 | 92.47% | **74.06%** | 0.6661 | 0.6672 | 5,602 | 16.41 MiB |

Complete-Evidence Recall is the protocol's primary retrieval metric. The 256/0
and 512/64 conditions tie on that metric at K=10. The 256/0 condition has the
best Any-Evidence Recall, MRR, and nDCG@10, and uses no overlap. It is therefore
the simplest configuration that is not materially worse.

## Frozen Selection

Freeze **256 model-input tokens with zero overlap** as the B2 Dense baseline.
The model revision, CPU device, query instruction, page aggregation, and
reported K values remain fixed in
`configs/dense_bge_small_en_v1_5_selected_v0.json`.

This selection does not mean Dense retrieval is finished as a research topic.
It creates a stable baseline against which the already-observed sparse/dense
complementarity and any single failure-driven improvement can be tested. The
calibration and locked-test splits remain untouched.
