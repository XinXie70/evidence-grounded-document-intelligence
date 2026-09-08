# Day 4 Two-Case Actual Reliability Demonstration v0

## Scope

This report applies the deterministic Reliability scorer to the prompt-matched C1 and C2 results
for `smoke_01` and `smoke_03`. Both cases are benchmark-answerable. The two-case set is a teaching
and pipeline-validation fixture, not a performance sample.

## Audited outcomes

| Condition | smoke_01 | smoke_03 |
|---|---|---|
| C1 Real Retrieval | grounded success | appropriate abstention because required evidence was missing |
| C2 Oracle Page | grounded success | correct answer with incomplete citation chain |

## Metrics

| Metric | C1 Real Retrieval | C2 Oracle Page |
|---|---:|---:|
| Coverage | 0.50 | 1.00 |
| Selective risk | 0.00 | 0.00 |
| Grounded selective risk | 0.00 | 0.50 |
| Benchmark task accuracy | 0.50 | 1.00 |
| Strict grounded task accuracy | 0.50 | 0.50 |
| Contextual reliability accuracy | 1.00 | 0.50 |

## Interpretation

- `coverage` asks how often the system answered. C1 answered one of two; C2 answered both.
- `selective_risk` asks how often an issued answer was wrong. Every issued answer was correct.
- `grounded_selective_risk` also treats incomplete grounding as an error. C2 issued two answers,
  and `smoke_03` omitted required page 31 from its citations, so the rate is one out of two.
- `benchmark_task_accuracy` treats abstention on an answerable benchmark question as failure even
  when the supplied context was inadequate. C1 therefore receives one correct result out of two.
- `contextual_reliability_accuracy` asks whether the model behaved safely given the context it
  actually received. C1 gets both cases right: answer when supported, abstain when evidence is
  missing. C2 loses `smoke_03` because a correct answer with an incomplete evidence chain is not
  fully reliable under the frozen definition.

No threshold or benchmark-wide conclusion may be selected from two cases.
