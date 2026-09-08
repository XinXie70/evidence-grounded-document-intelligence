# Day 4 Three-Case Actual Reliability Demonstration v1

## Scope

This report applies the deterministic Reliability scorer to the prompt-matched C1 and C2 results
for `smoke_01`, `smoke_03`, and `smoke_10`. The first two questions are answerable; `smoke_10` is
benchmark-unanswerable. Its empty-context C0 and C2 model requests were byte-identical, so one
immutable response was reused for both logical conditions.

This three-case set is a teaching and integration artifact, not a performance sample.

## Audited outcomes

| Condition | smoke_01 | smoke_03 | smoke_10 |
|---|---|---|---|
| C1 Real Retrieval | grounded success | appropriate abstention; required page missing | correct abstention on unanswerable question |
| C2 Oracle Page | grounded success | correct answer; citation chain incomplete | correct abstention; empty request reused from C0 |

## Metrics

| Metric | C1 Real Retrieval | C2 Oracle Page |
|---|---:|---:|
| Coverage | 0.333 | 0.667 |
| Selective risk | 0.000 | 0.000 |
| Grounded selective risk | 0.000 | 0.500 |
| Benchmark task accuracy | 0.667 | 1.000 |
| Strict grounded task accuracy | 0.667 | 0.667 |
| Contextual reliability accuracy | 1.000 | 0.667 |
| Unanswerable false-answer rate | 0.000 | 0.000 |
| Answerable abstention rate | 0.500 | 0.000 |
| Over-abstention rate on sufficient answerable context | 0.000 | 0.000 |

## Interpretation

- C1 answers only `smoke_01`; its two abstentions are appropriate for the supplied context, so
  contextual reliability is three out of three even though benchmark task accuracy is two out of
  three.
- C2 restores the correct answer for `smoke_03`, raising answer accuracy and coverage. Its omitted
  page-31 citation leaves one of two issued answers incompletely grounded.
- Both C1 and C2 correctly abstain on the unanswerable `smoke_10`; the tempting C1 pages do not
  produce a false tax-rate answer in this case.
- Zero errors over one unanswerable question is a case result, not a benchmark-wide rate claim.

## Day 4 matched-call accounting to this point

- `smoke_01`: 3 paid calls, USD 0.007281;
- `smoke_03`: 3 paid calls, USD 0.006901;
- `smoke_10`: 2 paid calls for 3 logical conditions, USD 0.012210;
- total: 8 paid calls, USD 0.026392.
