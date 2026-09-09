# Day 6 q3 Deterministic Comparison Consistency Check v0

## Purpose

Test whether a local, non-LLM reliability guard can detect the comparative
polarity error in the q3 layout-facts reasoning result.

## Inputs

The checker receives:

- the explicit `A more ... than B` question;
- two ordered facts produced by the layout fact selector;
- the model's structured answer output.

It does not read the benchmark answer and makes no paid request.

## Deterministic calculation

```text
left operand  = 10.8 hours
right operand = 287.4 minutes / 60 = 4.79 hours
signed difference = 10.8 - 4.79 = +6.01 hours
expected direction = more
```

The model answer contains the correct magnitude `6.01` but uses `fewer` and does
not use `more`. The checker therefore reports:

```text
numeric_magnitude_correct: true
comparative_direction_correct: false
accepted: false
policy_action: reject_and_abstain_or_regenerate
```

## Interpretation

The guard converts a structurally valid, correctly cited, but semantically
self-contradictory response into a safe rejection. This demonstrates a concrete
Reliability / Selective Answering mechanism rather than relying on the model's
self-reported status alone.

## Scope decision

Retain the checker as a tested diagnostic component. It currently supports only
explicit `more ... than` comparisons over exactly two ordered hours/minutes facts.
Do not apply it to unrelated question forms or claim corpus-level improvement
until broader development-tune evaluation is designed.

