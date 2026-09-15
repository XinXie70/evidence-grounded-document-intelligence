# V1 One-Time Locked-Test Report

**Split:** `locked_test`

**Evaluation date:** 2026-09-14 to 2026-09-15 (Australia/Sydney)

**Scope:** 730 questions from 156 previously locked documents

**Status:** complete; V1 remains frozen and no locked-test result is used to modify V1

## Executive result

The frozen V1 system answered 436 of 730 questions (59.73% coverage). It was task-correct on
311/730 questions (42.60%) and both task-correct and evidence-supported on 291/730 questions
(39.86%). Among questions for which the system produced an answer, task accuracy was 284/436
(65.14%) and strict grounded accuracy was 264/436 (60.55%).

This is a meaningful end-to-end result on an untouched test split, but it is not production-grade.
The locked test reveals a substantial generalization gap relative to calibration, with evidence
retrieval/selection and abstention policy remaining the main limitations.

## Primary metrics

| Metric | Locked-test result |
|---|---:|
| Questions / documents | 730 / 156 |
| Answered / abstained | 436 / 294 |
| Coverage | 59.73% |
| Task accuracy, all questions | 311/730 (42.60%) |
| Grounded accuracy, all questions | 291/730 (39.86%) |
| Task accuracy among answered questions | 284/436 (65.14%) |
| Grounded accuracy among answered questions | 264/436 (60.55%) |
| Evidence support among answered questions | 374/436 (85.78%) |
| Any gold-page recall, eligible answerable questions | 54.42% |
| Complete gold-page recall, eligible answerable questions | 38.05% |
| Mean final cited-page precision / recall / F1 | 51.52% / 44.89% / 46.16% |

Evidence support over all 730 questions is 667/730 (91.37%), but this number is not a useful answer
quality metric because abstentions make no answer claim and are counted as supported. The
answered-only value, 85.78%, is the interpretable support metric.

## Bootstrap uncertainty

Intervals use 10,000 deterministic percentile-bootstrap replicates with seed `20260827`.
Document-clustered intervals resample the 156 documents and are the more conservative primary
uncertainty estimate because multiple questions can come from the same document.

| Metric | Point estimate | Question bootstrap 95% CI | Document-clustered 95% CI |
|---|---:|---:|---:|
| Task accuracy | 42.60% | 39.04%–46.30% | 38.29%–46.78% |
| Grounded accuracy | 39.86% | 36.30%–43.42% | 35.48%–44.04% |
| Coverage | 59.73% | 56.16%–63.29% | 55.34%–63.92% |
| Selective task accuracy | 65.14% | 60.63%–69.63% | 60.14%–69.96% |
| Selective grounded accuracy | 60.55% | 55.91%–65.06% | 54.99%–65.82% |
| Any evidence recall | 54.42% | 50.60%–58.27% | 49.78%–58.91% |
| Complete evidence recall | 38.05% | 34.32%–41.78% | 33.24%–42.90% |

## Answerability behavior

Of the 679 gold-answerable questions, V1 answered 413 and produced a correct answer for 284. This
corresponds to 41.83% task recall over answerable questions; 264/679 (38.88%) were strictly grounded
correct. Among the 413 attempted answerable questions, 284 (68.77%) were correct.

Of the 51 gold-unanswerable questions, V1 correctly rejected 27 (52.94%) and incorrectly answered
23. One additional null operational failure is conservatively not credited as a correct rejection.

## Route diagnostics

| Route | Questions | Coverage | Task accuracy | Grounded accuracy | Selective task accuracy | Selective grounded accuracy |
|---|---:|---:|---:|---:|---:|---:|
| R0 native text | 494 | 59.72% | 43.93% | 40.69% | 64.41% | 58.98% |
| R1 local visual | 184 | 70.65% | 47.28% | 45.11% | 66.92% | 63.85% |
| R2 scanned document | 19 | 57.89% | 36.84% | 36.84% | 63.64% | 63.64% |
| R3 document-global | 33 | 0.00% | 0.00% | 0.00% | n/a | n/a |

R1 has the strongest observed route-level metrics, showing that the bounded visual recovery path is
useful. This table is diagnostic, not a causal comparison: questions are routed by difficulty and
the route populations are not randomized. R3 is an explicit capability boundary in V1; the frozen
policy abstains on document-global questions, so all 33 received zero task credit.

## Calibration-to-test generalization

| Metric | Development calibration | Locked test | Change |
|---|---:|---:|---:|
| Coverage | 56.06% | 59.73% | +3.67 pp |
| Selective task accuracy | 87.84% | 65.14% | -22.70 pp |
| Selective grounded accuracy | 79.73% | 60.55% | -19.18 pp |

The confidence policy preserved approximately the intended coverage, but answer correctness at that
coverage generalized substantially worse than on the 132-question calibration split. This supports
the calibration report's earlier conclusion that the confidence ordering was weak and should not be
described as a calibrated probability.

## Retrieval-metric boundary

The 38.05% complete-evidence figure above measures whether the **final cited pages** contain every
gold evidence page. It is not directly comparable to the earlier 77.41% RRF Complete Evidence
Recall@10 development result, which measures whether a wider ten-page retrieval candidate set
contains every gold page. The difference reflects both the evaluation split and the narrowing from
retrieval candidates to final evidence/citations.

## Operational integrity

- All 730 frozen prediction records were included.
- All 849 required judge outputs were present and validated: 413 semantic judgments and 436
  evidence-support judgments.
- Six preserved answer-generation API failures and one invalid structured prediction were counted
  conservatively as task failures; none was silently dropped.
- The operational-failure rate was 6/730 (0.82%); the invalid-prediction rate was 1/730 (0.14%).
- The full deterministic suite passed 377/377 tests after final scoring and reporting changes.
- Successful/preserved answer-generation records account for approximately USD 4.1437, and 24
  preserved failed attempts account for approximately USD 0.1998. The 849 final judge requests
  account for USD 1.8961.

## Interpretation and limitations

V1 demonstrates a complete and auditable evidence-grounded document QA system rather than a toy
prompt wrapper: isolated splits, hybrid retrieval, bounded OCR/visual recovery, citations,
abstention, immutable prediction artifacts, cost controls, independent semantic/support judgments,
and clustered uncertainty are all exercised end to end.

The final numbers also establish clear limits. Complete final evidence coverage is low, multi-page
evidence is often lost during evidence narrowing, R3 document-global questions are unsupported,
the abstention gate does not generalize as strongly as calibration suggested, and a meaningful share
of produced answers remains wrong despite valid citations. V1 should therefore be presented as a
rigorously evaluated research/engineering prototype, not as a production-ready document QA system.

Any improvement informed by these locked-test outcomes must be developed as V2 on development data
and evaluated on a new untouched test set. The reported V1 result must not be overwritten or tuned
against this locked test.

## Immutable result artifacts

- Automatic audit and point estimates: `results/v1_locked_test_score_v0.json`
- Bootstrap intervals: `results/v1_locked_test_bootstrap_v0.json`
- Frozen scoring protocol: `V1_CALIBRATION_SCORING_PROTOCOL.md`
- One-time test protocol: `V1_LOCKED_TEST_PROTOCOL.md`
- Frozen system manifest: `experiments/v1_system_freeze_manifest_v1.json`
