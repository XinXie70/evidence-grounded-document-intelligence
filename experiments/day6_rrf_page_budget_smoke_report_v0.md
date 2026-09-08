# Day 6 RRF reasoning page-budget smoke v0

## Question

When RRF supplies candidate physical PDF pages to the same grounded-reasoning model,
does a page budget of 3, 5, or 10 give the best observed balance of evidence coverage,
answer correctness, and API cost?

## Frozen design

- Split: `development_tune` only.
- Retriever: `hybrid_rrf_bm25_dense_v0`.
- Three deterministic questions represent evidence complete at Top-3, newly complete at
  Top-5, and newly complete at Top-10.
- Conditions per question: K=3, K=5, K=10.
- Model and prompt contract are identical across all nine calls.
- No gold answer or gold page label appears in model input.

All 9/9 calls completed successfully. The observed total cost was `$0.0876065`.

## Strict observed results

| Case | K=3 | K=5 | K=10 |
|---|---:|---:|---:|
| POPIA age threshold | correct | correct | correct |
| District population difference | wrong: 82,210 | correct: 91,330 | wrong: 82,210 |
| Weekday activity difference | wrong: 6.0 | wrong: 6.0 | wrong: 6.0 |

| Metric | K=3 | K=5 | K=10 |
|---|---:|---:|---:|
| Answer rate | 100% | 100% | 100% |
| Citation-contract validity | 100% | 100% | 100% |
| Strict benchmark accuracy | 33.3% | 66.7% | 33.3% |
| Observed cost | $0.0154735 | $0.0276645 | $0.0444685 |

## Failure analysis

### Competing population tables

The district-population question has two highly plausible tables. Physical page 11 reports
the population aged 10 years and over and yields 82,210. Physical page 19 reports all persons
and yields the benchmark answer 91,330. The question itself says only “the population
distribution table broken down by district,” so it does not explicitly distinguish these
two populations. K=10 contained the gold page but the model selected the competing page-11
table. This is both a context-selection failure and a benchmark-ambiguity warning.

### Rounded direct table versus precise multi-page evidence

The activity question's page 21 directly reports 10.8 hours for male personal care and
4.8 hours for female housework/family care, yielding 6.0 hours. The benchmark instead pairs
10.8 hours from page 21 with the more precise 287.4 minutes from page 55, yielding 6.01 hours.
K=10 contained both gold pages, but the model preferred the direct same-table comparison.
This is an evidence-granularity and multi-hop selection failure, not a retrieval miss.

## Decision

Do not freeze K=5 from only three cases, and do not assume that increasing K improves final
answers. RRF Top-10 remains useful as a high-coverage candidate pool, but all ten full pages
should not automatically become reasoning context. The next bounded experiment should keep
the Top-10 candidate pool and test question-aware evidence reduction inside that pool.

The observed ambiguous cases must remain explicit audit slices rather than being silently
counted as generic LLM failures.
