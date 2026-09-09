# Frozen Generic Comparison Validation v0

## Purpose

Evaluate the frozen generic comparison pipeline on six development-tune questions
from documents excluded from method development. Case selection used question text
and the existing RRF Top-10 page order, but not gold answers or gold evidence pages.

Pipeline:

`RRF Top-10 -> model fact extraction -> deterministic arithmetic -> numeric citation verification -> frozen citation repair -> post-hoc scoring`

## Results

| Metric | Result |
|---|---:|
| Cases | 6 |
| Answer exact match | 4/6 (66.7%) |
| Complete benchmark evidence match | 5/6 (83.3%) |
| Answered cases | 5/6 (83.3% coverage) |
| Accuracy among answered cases | 4/5 (80.0%) |
| Answers with locally verified numeric citations | 5/5 (100%) |
| Paid API cost | $0.078233 |

No citation repair was required in this validation batch. One case abstained and
five answered cases cited pages on which their reported numeric values occurred.

## Case outcomes

| Case | Outcome | Answer | Evidence | Interpretation |
|---|---|---:|---:|---|
| validation_01 | Abstained | Fail under answer benchmark | Incomplete retrieval | Appropriate selective behavior given supplied context |
| validation_02 | Answered | Correct (96) | Complete | Success |
| validation_03 | Answered | Correct (403) | Complete | Success |
| validation_04 | Answered | Correct (5,383) | Complete | Success |
| validation_05 | Answered | Incorrect (35.5 vs 37.0) | Complete | Layout-to-value association failure |
| validation_06 | Answered | Correct (0.31) | Complete | Success |

## Failure analysis

### validation_01: retrieval coverage

The ZIP-code comparison requires two mailing-address pages. RRF Top-10 supplied
physical page 4 but omitted physical page 3. The model returned
`insufficient_evidence` instead of guessing. This is a retrieval-stage failure and
a reliability-stage success.

### validation_05: layout-aware fact association

The correct waterfall-chart pages (22 and 23) were retrieved. On page 23, flattened
text detached chart labels from their bars. The model associated `(3.5)` with
`Difference of Non-recurring cost`; the chart association required `(2.0)`. The
deterministic calculator correctly computed the supplied operands, but the selected
second operand was wrong. This is a layout-aware fact-extraction failure rather than
an arithmetic or page-retrieval failure.

## Change control

These six outcomes are frozen and must not be replaced or rescored after per-case
method tuning. The observed failures are retained for the project error taxonomy.
Future work may evaluate multi-page retrieval expansion and chart-aware extraction,
but neither is required for the current portfolio MVP.

## Provenance

- Finalized predictions SHA-256: `babd6b285b4aca1694cb2ac29e01ed416f17751256f04ab8f57ee0263e55c768`
- Citation audit SHA-256: `9ecf01ba77987926779b60c0a48c2e20fe6834cb210aaf3697c88a735a53a484`
- Citation-repaired predictions SHA-256: `dd21f96e2166269ffb20234ae8f8879eb089ad31cff5a7c0362a944e1d96652b`
- Post-hoc score SHA-256: `313717d597353016f18e347a5cd70d0adbfed30e77fb303c712762a6dc898ad9`
