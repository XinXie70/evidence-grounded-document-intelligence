# Day 4 Abstention Pair Demonstration v0

## Purpose

This two-record diagnostic shows why `insufficient_evidence` is an action, not automatically a
successful Reliability outcome. Both source responses abstained, but the contexts differed.

## Contrast

| Case | Audited context | Response | Reliability outcome |
|---|---|---|---|
| smoke_03 C1 Real Retrieval | insufficient; required page 40 missing | abstain | appropriate abstention given context |
| smoke_06 contextual C3 | sufficient; both exact table facts manually verified | abstain | over-abstention |

## Metric interpretation

- coverage is 0 because neither record was answered;
- benchmark task accuracy is 0 because both benchmark questions are answerable;
- contextual reliability accuracy is 0.5 because only one of the two abstentions is appropriate;
- over-abstention rate on sufficient answerable context is 1.0 in its one-case denominator;
- appropriate-abstention rate on insufficient context is 1.0 in its one-case denominator;
- selective risk and grounded selective risk are `null`, not zero, because there are no issued
  answers on which to calculate error rates.

This is a teaching contrast with denominators of one, not a model-performance estimate.
