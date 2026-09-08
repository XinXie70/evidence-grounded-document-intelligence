# Day 4 Reliability / Selective Answering Protocol v0

## Purpose

This document turns the frozen evaluation protocol into deterministic outcome labels and aggregate
metrics. It does not select a confidence signal, fit a threshold, or make population claims from
the small smoke set.

## Two different questions

Every audited response is evaluated on two axes:

1. **Benchmark task result:** Did the system produce the correct final answer, or correctly abstain
   on a benchmark-unanswerable question?
2. **Contextual reliability behavior:** Given the evidence actually supplied in this condition,
   was answering or abstaining appropriate?

These axes must remain separate. An answerable benchmark question with incomplete retrieved
evidence can produce an appropriate abstention but still count as an end-to-end task failure.

## Frozen outcome labels

| Benchmark / context / response | Outcome label | Task correct | Contextually reliable |
|---|---|---:|---:|
| Answerable; answered correctly; fully grounded | `grounded_success` | yes | yes |
| Answerable; answer correct; grounding incomplete | `correct_answer_incomplete_grounding` | yes | no |
| Answerable; answered incorrectly | `incorrect_answer` | no | no |
| Answerable; evidence insufficient; abstained | `appropriate_abstention_given_context` | no | yes |
| Answerable; evidence sufficient; abstained | `over_abstention` | no | no |
| Unanswerable; abstained | `correct_abstention` | yes | yes |
| Unanswerable; answered | `false_answer_on_unanswerable` | no | no |

`evidence_sufficient` is an **audit-only label** derived from gold conditions and manual review. It
must never be used as an inference-time confidence feature or threshold input.

## Deterministic aggregate metrics

- `coverage = answered / all questions`
- `selective_risk = incorrect answered questions / answered questions`
- `grounded_selective_risk = answered questions without grounded correctness / answered questions`
- `benchmark_task_accuracy = task-correct questions / all questions`
- `strict_grounded_task_accuracy = grounded-correct answerable questions plus correct unanswerable abstentions / all questions`
- `contextual_reliability_accuracy = contextually reliable actions / all questions`
- `unanswerable_false_answer_rate = answered unanswerable questions / unanswerable questions`
- `answerable_abstention_rate = abstained answerable questions / answerable questions`
- `over_abstention_rate_on_sufficient_answerable = abstentions / answerable questions with audited sufficient evidence`
- `appropriate_abstention_rate_on_insufficient_context = abstentions / answerable questions with audited insufficient evidence`

Rates with a zero denominator are reported as `null`, not zero.

## Inputs that are not yet frozen

Risk-coverage curves and AURC require a scalar confidence signal available at inference time. No
such signal is selected yet. Candidate signals may be evaluated later on
`development_calibration`, but gold answerability, gold evidence coverage, Oracle condition labels,
manual correctness, and `evidence_sufficient` are forbidden features.

The 100%, 90%, 80%, and 60% coverage operating points will be computed only after:

1. a candidate inference-time signal is explicitly named;
2. its direction and tie-breaking rule are frozen;
3. thresholds are fitted only on `development_calibration`;
4. the answer and grounding evaluator configuration is frozen.

## Smoke fixture limitation

`day4_reliability_smoke_fixture_v0.json` contains five manually audited examples chosen to exercise
different labels. Its aggregate output validates implementation behavior only and must not be
reported as system performance.
