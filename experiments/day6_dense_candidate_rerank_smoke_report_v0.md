# Day 6 dense candidate-reranking smoke v0

## Intervention

RRF Top-10 remains the label-free high-coverage candidate pool. The frozen BGE dense scorer
reranks only those candidates using the full question. The top two selected physical pages
are then supplied in full to grounded reasoning. Chunking is used only for page scoring;
partial chunks are not used as reasoning evidence.

The selected pages were:

- POPIA threshold: 12, 17.
- District population difference: 12, 19.
- Weekday activity difference: 21, 55.

All three selections contained every DocScope gold page for their question.

## Observed reasoning results

| Case | Strict result | Citation |
|---|---|---|
| POPIA threshold | correct: 18 years | page 12 |
| District population difference | correct: 91,330 | page 19 |
| Weekday activity difference | wrong: 6.0 vs 6.01 | page 21 only |

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
