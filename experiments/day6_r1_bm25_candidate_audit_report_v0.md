# Day 6 R1 BM25 Candidate Audit v0

**Split:** development_tune only  
**API cost:** USD 0  
**Decision:** do not freeze the first R1 candidate yet

## Question

For a question that explicitly mentions a chart, table, figure, image, map, or
similar visual structure, is it sufficient to retrieve BM25's top pages and
send those page images to the reasoning model?

This audit tests only the first half of that proposed route: whether the page
candidate set contains the benchmark evidence. It makes no visual-model call.

## Population

The frozen router assigns 64 eligible tune questions across 39 documents to
R1. Thirty questions need one evidence page; the other 34 need multiple pages,
including one question with seven evidence pages. Complete-evidence recall is
therefore more important than finding just one relevant page.

## Results

| Candidate set | Any evidence | Complete evidence |
|---|---:|---:|
| BM25 Top 3 | 71.9% | 46.9% |
| BM25 Top 5 | 79.7% | 57.8% |
| BM25 Top 10 | 90.6% | 79.7% |

At Top 10, 13 of 64 questions still lack at least one required evidence page;
six contain no required evidence page at all.

## Interpretation

The R1 trigger is not itself enough to make visual answering work. The system
must first discover the correct page. Rendering the wrong BM25 pages at higher
visual quality cannot recover missing evidence.

The failure occurs before the visual reasoning model:

```text
question -> BM25 candidate pages -> page images -> visual reasoning
                ^
          current failure point
```

The next step is to inspect only the 13 tune failures and determine whether
they are caused by adjacent multi-page evidence, sparse page text, lexical
mismatch, or document-global scope. Only an observed failure type may justify
the next bounded R1 candidate-generation change.

Candidate generation used no gold labels. Gold pages were consulted only after
ranking to compute these tune metrics. Calibration labels and locked-test data
were not accessed.
