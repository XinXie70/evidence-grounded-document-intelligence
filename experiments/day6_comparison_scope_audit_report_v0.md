# Day 6 Comparison Reliability Scope Audit v0

## Scope

This audit inspects only answerable `development_tune` questions. It does not
evaluate calibration or locked-test questions and makes no paid API request.

There are 239 answerable questions in the tune split.

## Results

| Question wording family | Questions | Share of 239 |
|---|---:|---:|
| Strict `more ... than` currently supported | 2 | 0.84% |
| Directional families after a bounded extension | 10 | 4.18% |
| Union of directional and `difference` wording | 41 | 17.15% |

The proposed directional extension consists of:

- 2 strict `more ... than` questions;
- 1 strict `less ... than` question;
- 7 `more/higher/larger/less/lower/fewer ... compared to` questions.

The remaining comparison family contains 31 questions using `difference` or
`differ`. These questions cannot automatically reuse the polarity rule because
many request an absolute magnitude rather than a directional `more` or `fewer`
statement.

## Decision

The current checker is a narrow q3-driven reliability guard, not a general
solution. Its direct coverage is 0.84%. However, deterministic comparison checks
are potentially relevant to 17.15% of answerable tune questions.

The next safe extension should cover only the 10 direction-explicit questions and
must be validated locally before any additional reasoning calls. Absolute
`difference` questions remain a separate future rule family.

