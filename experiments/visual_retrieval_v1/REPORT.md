# Question-Conditioned Visual Retrieval v1

## Decision

**Keep the visual reranker.** It passed every condition in the preregistered gate on the full
63-question R1 `development_tune` slice. No benchmark answer or gold-evidence field was available
to the rendering, encoding, or ranking path.

This is a page-ranking result, not a claim that region localization, answer generation, or
held-out generalization has been solved. Calibration and the locked test remained untouched.

## What changed

The previous visual ablation only detected whether a page contained a table, image, or vector
object. That label-free signal did not distinguish the relevant page from visually similar
distractors.

The v1 candidate keeps the frozen equal-weight BM25 + BGE RRF Top-10 pool and changes only its
order:

```text
RRF Top-10 pages
  -> render full physical pages at 150 DPI
  -> encode question and pages with pinned ColSmol-256M
  -> ColBERT-style late-interaction score
  -> visual reranking with stable RRF tie-break
```

The candidate uses the off-the-shelf model without DocScope-specific training or per-question
rules. There was no paid API use.

## Frozen evaluation

| Metric | Original RRF | Visual rerank | Net change |
|---|---:|---:|---:|
| Any Evidence Recall@1 | 33/63 (52.38%) | 40/63 (63.49%) | +7 |
| Complete Evidence Recall@1 | 16/63 (25.40%) | 18/63 (28.57%) | +2 |
| Any Evidence Recall@3 | 50/63 (79.37%) | 57/63 (90.48%) | +7 |
| Complete Evidence Recall@3 | 35/63 (55.56%) | 42/63 (66.67%) | +7 |
| Any Evidence Recall@5 | 57/63 (90.48%) | 60/63 (95.24%) | +3 |
| Complete Evidence Recall@5 | 44/63 (69.84%) | 50/63 (79.37%) | +6 |
| Any Evidence Recall@10 | 60/63 (95.24%) | 60/63 (95.24%) | 0 |
| Complete Evidence Recall@10 | 55/63 (87.30%) | 55/63 (87.30%) | 0 |
| MRR@10 | 0.6791 | 0.7590 | +0.0799 |
| nDCG@10 | 0.7168 | 0.7670 | +0.0502 |

Top-10 recall is unchanged by construction because this experiment only reorders the same ten
pages. Its value is moving useful evidence into the smaller Top-3 and Top-5 budgets consumed by a
downstream reasoner.

The paired Complete@3 outcome was 11 gains, 4 losses, 31 shared successes, and 17 shared failures.
At Complete@5 it was 7 gains, 1 loss, 43 shared successes, and 12 shared failures. Reporting the
losses prevents the positive net result from hiding regressions on individual questions.

## Page-span slices

| Slice | Questions | Original Complete@3 | Visual Complete@3 | Original Complete@5 | Visual Complete@5 |
|---|---:|---:|---:|---:|---:|
| Single-page evidence | 30 | 80.00% | 90.00% | 90.00% | 96.67% |
| Multi-page evidence | 33 | 33.33% | 45.45% | 51.52% | 63.64% |

The improvement is therefore not limited to easy single-page questions; the multi-page slice also
gains four complete-evidence questions at both Top-3 and Top-5.

## Gate audit

The preregistered gate required at least four additional Complete Evidence successes at Top-3 or
Top-5, no Complete decrease at the other cutoff, no more than one Any Evidence loss at either
cutoff, all 63 questions through one generic path, and intact physical-page provenance.

All checks passed:

- Complete net change: +7 at Top-3 and +6 at Top-5;
- Any Evidence paired losses: one at Top-3 and zero at Top-5, with net changes of +7 and +3;
- 63/63 questions used the same implementation;
- every reranked list retained exactly its original RRF candidate-page set.

## Runtime and reproducibility

- Unique candidate pages: 503 across 38 documents.
- Rendered-page cache: 503 PNG files, 130,150,221 bytes.
- Page-embedding cache: 503 NumPy files, 247,451,520 bytes.
- Cache-hit query and ranking pass: 3.668 seconds for 63 questions, about 58 ms/question,
  excluding model loading.
- A second blind cache-hit run reproduced all 63 rankings and every recorded score exactly.
- The interrupted/resumed build intentionally preserved completed artifacts. Its final segment
  encoded 213 previously uncached pages plus all queries in 512.181 seconds. The initial segment's
  active compute time was not separately instrumented, so this report does not claim a precise
  end-to-end cold-build latency.
- Full deterministic suite after implementation: 311/311 tests passed.
- Paid API cost: USD 0.

## Immutable artifacts

- Runtime manifest SHA-256:
  `b5d415b0a0dcad6f1e596616d4a8391d63486cf0ef087f327ad529e3516f8265`
- Primary blind ranking SHA-256:
  `a42e3d90576e60653b0e15830e64d98ab2d6aea52d435aa634ec7c42c2a1ec50`
- Post-hoc evaluation SHA-256:
  `57978ad5193a79e7add553251703e8c7b53ce179f8d0351230f5311f4f0fe35f`

The raw PDFs, rendered pages, model cache, and page embeddings are local ignored artifacts and are
not redistributed.

## Limitations and next step

This evaluation selected one pretrained public model and used only the R1 tune slice. Unknown
pretraining overlap with source documents remains a limitation. Full-page visual similarity also
does not prove fine-grained region grounding, and four Complete@3 questions regressed even though
the net result improved.

Following the completion protocol, the next step is not another visual model or post-hoc weight
tuning. The retained visual reranker should be integrated as the frozen R1 candidate, after which
the reliability policy is calibrated on the untouched calibration split. Only then may the locked
test be opened once for final evaluation.
