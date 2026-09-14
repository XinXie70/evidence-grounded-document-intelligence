# V1 Calibration Threshold Correction

**Status:** frozen before locked-test access
**Date:** 2026-09-14 (Australia/Sydney)

## What was corrected

The frozen calibration protocol defines coverage over all evaluation questions. The first threshold
artifact instead selected among answer-retention points, whose denominator was only the 74
policy-eligible candidate answers. Calling those points the predeclared coverage targets was a
definition mismatch.

The original artifact, `configs/confidence_threshold_v1_calibration_v0.json`, is retained unchanged
for audit. It is superseded by `configs/confidence_threshold_v1_calibration_v1.json`. No locked-test
question, label, Page Record, retrieval result, or model output was accessed to make this correction.

## Correct protocol interpretation

There are 132 calibration questions and 74 policy-eligible answers, so the maximum attainable
coverage is 74 / 132 = 56.06%. Consequently, the predeclared 60%, 80%, 90%, and 100% total-question
coverage targets all resolve to the same conservative boundary: confidence 0.3566666666666667,
74 answered questions, and 56.06% achieved coverage.

The corrected V1 decision rule is:

1. retain an answer only when the frozen eligibility rule passes; and
2. require confidence >= 0.3566666666666667.

At calibration this threshold adds no further rejection beyond the eligibility gate. The confidence
ordering is therefore reported as a weak/negative calibration result, not as a calibrated
probability or evidence of monotonic risk reduction.

## Why the more restrictive V0 threshold was not retained

The V0 threshold of 0.40705128205128205 retained 59 answers. Relative to the corrected boundary, it
improved task accuracy among answered questions only from 87.84% to 88.14% and grounded accuracy
among answered questions from 79.73% to 81.36%, while discarding 15 additional answers, including
13 task-correct answers. That trade-off was neither justified by the original coverage protocol nor
large enough to support a post-hoc replacement objective.
