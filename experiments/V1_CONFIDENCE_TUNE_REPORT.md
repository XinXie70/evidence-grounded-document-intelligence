# V1 Confidence Tune Report

**Status:** keep gate passed; calibration may be prepared but remains unopened
**Split:** `development_tune` only
**Date:** 2026-09-11

## What was evaluated

The current V1 pipeline produced one answer-or-abstain decision for each of the frozen 24-question
reliability cases. Two R2 cases use the corrected layout-preserved OCR evidence packages. All
predictions and label-free features were frozen before benchmark answers and human outcome labels
were joined.

The human audit records two different outcomes:

- `task_correct`: the final answer is correct, or an unanswerable question is correctly rejected;
- `grounded_correct`: the task outcome is correct and every material claim is supported by its
  cited supplied pages.

The user explicitly confirmed the complete audit, including the boundary decision that `pilot_12`
is task-correct but not fully grounded because page 10 is materially required and was not cited.

## Audited pipeline outcomes

| Measure | Result |
|---|---:|
| Questions | 24 |
| Task-correct | 16 / 24 (66.67%) |
| Fully grounded-correct | 13 / 24 (54.17%) |
| Eligible answer outputs | 16 / 24 (66.67% coverage) |
| Incorrect among eligible answers | 4 / 16 (25.00% risk) |
| Incorrect or incompletely grounded among eligible answers | 7 / 16 (43.75% grounded risk) |

Correct abstentions count as correct task outcomes but are not eligible answered outputs. Therefore,
the 16 task-correct questions and the 16 eligible answers are different sets.

## Frozen confidence formula

The scalar score uses only signals available at inference time:

```text
confidence =
    0.65 * route_prior
  + 0.15 * query_token_coverage_ratio
  + 0.15 * citation_to_evidence_ratio
  + 0.05 * bm25_dense_agreement_at_10
```

Route priors are Beta(1,1)-smoothed grounded-success rates from eligible tune answers: R0 `1/3`,
R1 `5/6`, and R2 `3/4`. R3 has no eligible answer and retains the neutral `1/2` prior. Dense
agreement is unavailable on R2 and R3 and receives the frozen neutral missing value `0.5`.

The score does not use benchmark answerability, answers, gold pages, evidence recall, Oracle
conditions, or correctness labels at inference time. Formula weights, route priors, the missing
rule, eligibility rule, and question-ID tie-breaking are now frozen before calibration.

## Risk-coverage result

When eligible answers are ordered from highest to lowest confidence:

- the first 6 answers (25.00% total coverage) are all task-correct and fully grounded;
- the first 9 answers (37.50% total coverage) are all task-correct and fully grounded;
- the first grounding error enters at answer 10;
- the first task error enters at answer 11;
- all 16 eligible answers give 66.67% coverage, 25.00% task risk, and 43.75% grounded risk.

The tune AURC over eligible prefixes is `0.0714`; grounded AURC is `0.1271`. The required target
operating-point report is:

| Target coverage | Achieved coverage | Answered | Task risk | Grounded risk |
|---:|---:|---:|---:|---:|
| 100% | 66.67% | 16 | 25.00% | 43.75% |
| 90% | 66.67% | 16 | 25.00% | 43.75% |
| 80% | 66.67% | 16 | 25.00% | 43.75% |
| 60% | 58.33% | 14 | 21.43% | 35.71% |

The first three targets coincide because the reasoner and hard validity gate already limit maximum
answer coverage to 66.67%.

## Gate decision

**Keep.** Higher confidence has a clear directional association with grounded correctness on the
frozen tune cases: the high-confidence prefix is clean, and risk rises as lower-confidence answers
are admitted. Every score input is available for unseen questions through the generic R0-R3
pipeline.

This is a tune-only gate, not a final performance claim. The route-specific sample sizes are small,
especially R2, so calibration must test whether the ordering generalizes. Calibration may select
numeric thresholds only; it may not change features, weights, routes, retrieval, prompts, or
evidence packaging.

## Frozen artifacts

- Features: `experiments/v1_confidence_tune_features_v1.json`
  (`e456aed0291f2d40312ddb898f04357469d02430dda2f9840833b27646470690`)
- Human audit: `experiments/v1_confidence_tune_human_audit_v1.json`
  (`41e03f49044804a4878b16b28a5a917e8a8605bd705b6d2e859cf5e0b63225d8`)
- Confidence policy: `configs/confidence_policy_v1_tune_v0.json`
  (`d863b01f1d366f861630255513a8cd02033f22f1c25aa9b9bf1fa9911a800fd4`)
- Evaluation: `experiments/v1_confidence_tune_evaluation_v0.json`
  (`7c239a9b7e203949b67401d86264c8e4a96d713749c6ae9f338139924ea3b90e`)

The deterministic test suite passes 334 tests after the calibration-preparation safety tests were
added.
