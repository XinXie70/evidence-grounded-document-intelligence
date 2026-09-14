# V1 Reliability Calibration Report

**Split:** `development_calibration`

**Scope:** 132 questions from 35 documents isolated from method development

**Locked-test status:** untouched

## Frozen evaluation outcome

| Metric | Result |
|---|---:|
| Questions | 132 |
| Task-correct generations before selective filtering | 73/132 (55.30%) |
| Strict grounded-correct generations before selective filtering | 67/132 (50.76%) |
| Policy-eligible answers | 74/132 (56.06% coverage) |
| Task accuracy among eligible answers | 65/74 (87.84%) |
| Strict grounded accuracy among eligible answers | 59/74 (79.73%) |

The confidence policy is therefore useful mainly as a deterministic eligibility gate. Confidence
ordering did not justify rejecting additional eligible answers on this calibration split.

## Human audit

Fifty cases were sampled for human review. Task-correctness agreement was 50/50. For evidence
support, the reviewer made 37 independent decisions and agreed with the automatic judge on 34;
13 uncertain cases were subsequently resolved with the evidence shown, producing 47/50 final
agreement. Uncertainty was retained in the audit record rather than silently forced into a label.

## Threshold correction

The preregistered target referred to coverage over all 132 questions. The first V0 freeze file
mistakenly selected 80% retention among the 74 already eligible answers, which corresponds to only
44.70% total coverage. This was detected before locked-test access.

The corrected frozen threshold is `0.3566666666666667`. It retains all 74 eligible answers, yielding
the maximum attainable 56.06% coverage. Because the requested 60% total coverage was unattainable,
V1 does not describe the confidence score as a calibrated probability.

Per-question local artifacts remain excluded from the public repository. Their identities are
preserved in the V1 system-freeze manifest so the private experiment can still be audited.
