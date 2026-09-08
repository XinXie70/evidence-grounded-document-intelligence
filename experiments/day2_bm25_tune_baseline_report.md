# Day 2 Development-Tune Page-BM25 Baseline Report

## 1. Purpose and scope

This report freezes the first formal evidence-retrieval baseline on the
`development_tune` split. The system retrieves physical PDF pages; it does not generate answers.

The evaluated path is:

```text
PDF -> pinned pypdf text extraction -> Page Record -> page-level BM25 -> Top-K pages
```

No OCR, visual model, table reconstruction, semantic retriever, reranker, reasoning model,
agent, calibration data, or locked-test data is used.

## 2. Reproducibility identities

- Configuration: `configs/bm25_page_v0_tune.json`
- Configuration SHA-256:
  `891554561a80bff0c4b26ee33a7dffe3a147bc0d073a944732255f4674c4a6fb`
- Page Record manifest: `data/derived/page_records_manifest.json`
- Page Record manifest SHA-256:
  `634705896e8e796fa15c44b3e22968b0806797ba115cf5b7d3bde9eb7c1c2556`
- Result: `data/derived/bm25_page_v0_tune_results.json`
- Result SHA-256:
  `8dd53c91a53d517065e36609d984dca8c798b4fe9cba72aaeb5fe2dd4b5793c7`
- The evaluator was run twice and produced the same result SHA-256.
- All 44 discovered project tests passed at baseline completion.

## 3. Evaluation scope

| Item | Count |
|---|---:|
| Tune documents in corpus | 82 |
| Documents with eligible questions | 81 |
| Tune questions | 256 |
| Eligible answerable evidence questions | 239 |
| Unanswerable questions excluded from retrieval metrics | 17 |
| Single-page evidence questions | 86 |
| Multi-page evidence questions | 153 |

The one corpus document not represented in the retrieval denominator has only an unanswerable
tune question. It remains in the corpus and is not a processing failure.

## 4. Formal baseline result

| K | Any evidence | Complete evidence | Mean recall | Precision | MRR | nDCG |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.4770 | 0.1715 | 0.3106 | 0.4770 | 0.4770 | 0.4770 |
| 3 | 0.7155 | 0.4310 | 0.5573 | 0.3166 | 0.5830 | 0.5282 |
| 5 | 0.7741 | 0.5565 | 0.6580 | 0.2335 | 0.5960 | 0.5734 |
| 10 | 0.8954 | 0.7071 | 0.7960 | 0.1490 | 0.6119 | 0.6258 |

At K=10, 356 of 547 per-question gold-page occurrences are retrieved (micro recall 0.6508).
The difference from macro mean recall is expected because questions have different numbers of
gold pages.

## 5. Outcome buckets

These buckets are objective scorer outputs, not inferred causes.

| K | Complete | Partial | None | Total |
|---:|---:|---:|---:|---:|
| 5 | 133 | 52 | 54 | 239 |
| 10 | 169 | 45 | 25 | 239 |

`Partial` means at least one, but not every, gold page was retrieved. A later reasoner may produce
a plausible answer from partial evidence, so partial retrieval must not be treated as complete
support.

## 6. Main observable slices at K=10

### Single-page versus multi-page evidence

| Page span | Questions | Complete | Partial | None |
|---|---:|---:|---:|---:|
| Single | 86 | 78 | 0 | 8 |
| Multi | 153 | 91 | 45 | 17 |

Any-evidence success is similar for single-page and multi-page questions, but complete retrieval
is substantially harder for multi-page questions. Multi-page completion, rather than merely
finding a first relevant page, is the dominant structural retrieval challenge exposed by this
slice.

### Gold-page text status

| Gold-page text status | Questions | Complete | Partial | None |
|---|---:|---:|---:|---:|
| Normal text | 228 | 167 | 40 | 21 |
| Low text | 2 | 0 | 2 | 0 |
| At least one missing-text page | 9 | 2 | 3 | 4 |

Missing text creates a severe hard slice, but it is not the only or numerically largest source of
incomplete retrieval. Of the 70 questions not complete at K=10, 61 have normal text status. OCR
could address part of the missing-text slice but cannot by itself solve most baseline failures.
The two-question low-text slice is too small for a prevalence conclusion.

### Main evidence-type groups

| Evidence type | Questions | Complete | Partial | None |
|---|---:|---:|---:|---:|
| Text | 54 | 44 | 8 | 2 |
| Table | 78 | 59 | 10 | 9 |
| Chart | 17 | 13 | 2 | 2 |
| Mixed | 73 | 44 | 20 | 9 |

Small residual types are retained in the machine-readable result but omitted from this compact
table because their sample sizes range from one to seven. Text evidence is easiest in this
baseline. Mixed evidence has the lowest complete-retrieval rate among the four main groups.
Page retrieval for a table or chart does not establish that a later reasoner can read its values
or spatial relationships.

## 7. Manually verified failure attributions

The aggregate result supports prevalence statements about observable slices only. Causal labels
below are limited to examples whose PDF, Page Record, ranking, and benchmark evidence were
manually inspected.

| Question/case | Objective result | Verified dominant cause |
|---|---|---|
| Safe & Supported year comparison | Partial | Visible cover title absent from ordinary extractable text |
| Numbered Box callouts | Partial | Lexical ambiguity plus global multi-page enumeration |
| Focus-area paraphrase | Gold page rank 6 | Text-present semantic/paraphrase ranking limitation |
| Common violence factor | Complete at K=3 | Retrieval success; reasoning still required |
| Actual-house photograph count | Partial | Text-only Page Records do not represent image content |
| Rotated bird-registration document | No usable text corpus | Image-only document under the pinned extractor |

These cases establish that multiple pipeline stages can limit results. They do not yet provide a
complete causal census of all 70 K=10 incomplete questions.

## 8. Failure-driven decisions

1. Freeze text-only page BM25 v0 as the reproducible retrieval baseline.
2. Do not tune BM25 to compensate for image content it cannot observe.
3. Do not treat OCR as a general solution: most incomplete questions have normal extracted text.
4. Preserve complete-evidence metrics because multi-page partial retrieval is common.
5. Carry retrieval provenance and page identity into the reasoning stage.
6. Begin the smallest Grounded Reasoning baseline with both Oracle Evidence and BM25 evidence.
7. Use the Oracle-versus-BM25 answer gap to decide whether the next intervention belongs in
   retrieval, representation, or reasoning.

## 9. Readiness decision

The BM25 evidence-retrieval baseline is deterministic, tested, reproducible, split-safe, and
interpretable enough to serve as the first downstream input. Evidence Retrieval is not considered
solved; it is considered sufficiently measured to begin a minimal Grounded Reasoning experiment.
No calibration threshold or locked-test evaluation is authorized at this point.
