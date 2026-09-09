# Day 6 dense candidate-reranking smoke v0

## Intervention

RRF Top-10 remains the label-free high-coverage candidate pool. The frozen BGE dense scorer
reranks only those candidates using the full question. The top two selected physical pages
are then supplied in full to grounded reasoning. Chunking is used only for page scoring;
partial chunks are not used as reasoning evidence.

Terminology used below:

- **Dense-reranked Top-2 supplied pages** are the two pages selected from the RRF Top-10 and sent
  to the reasoner as input.
- **Benchmark evidence pages** are the DocScope gold pages used only for post-hoc evaluation.
- **LLM-cited pages** are the subset of supplied pages that the reasoner cited in its answer. A
  supplied page is not automatically a cited page.

| Case | Dense-reranked Top-2 supplied pages | Benchmark evidence pages | LLM-cited pages |
|---|---|---|---|
| POPIA threshold | 12, 17 | 12 | 12 |
| District population difference | 12, 19 | 19 | 19 |
| Weekday activity difference | 21, 55 | 21, 55 | 21 |

All three Top-2 input sets contained every DocScope evidence page for their question. The first
two questions required only one benchmark page, so the reasoner cited that supporting page rather
than both supplied pages. The weekday question required both supplied pages, but the reasoner
cited only page 21 and ignored the more precise value on page 55.

## Observed reasoning results

| Case | Strict result | Why |
|---|---|---|
| POPIA threshold | correct: 18 years | Gold page 12 was supplied and cited |
| District population difference | correct: 91,330 | Gold page 19 was supplied and cited |
| Weekday activity difference | wrong: 6.0 vs 6.01 | Both gold pages were supplied, but only page 21 was used and cited |

All 3/3 responses obeyed the citation/output contract. Strict benchmark accuracy was 2/3.
The total observed API cost was `$0.011465`.

Compared with the earlier three-question page-budget smoke, this preserved K=5's 2/3
strict accuracy while reducing observed cost by 58.6%. Compared with K=10, it improved
strict accuracy from 1/3 to 2/3 and reduced observed cost by 74.2%.

## Diagnosis

The activity failure is no longer attributable to page retrieval: both gold pages 21 and
55 were present. The model chose the direct rounded comparison on page 21 (10.8 minus 4.8)
and ignored the more precise 287.4-minute total on page 55 required by the benchmark.

This reproduces the earlier Oracle Page failure. The earlier Oracle Facts condition succeeded
with 6.01 when the two exact facts were supplied. Therefore the remaining bottleneck for this
case is fine-grained fact selection / grounded reasoning, not evidence-page retrieval.

## Decision

Do not adopt a fixed Top-2 page budget from three hand-inspected cases. Before another paid
reasoning run, evaluate candidate reranking locally across all eligible `development_tune`
questions at multiple output depths. This will measure the evidence-recall cost of context
reduction without touching calibration or locked test documents.
