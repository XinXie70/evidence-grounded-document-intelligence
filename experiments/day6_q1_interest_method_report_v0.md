# Day 6 simple-versus-compound total-interest comparison v0

## Question

How much more total interest does the compound-interest method accumulate than the
simple-interest method in the furniture purchase example?

## Observed ambiguity

Page 50 is the compound-interest example, but its flattened table text contains the
label `Simple Interest 3.33%`. Selecting a page from the last or nearest occurrence
of a method name could therefore assign the page to the wrong method.

## Label-free selection

The selector uses the question to order Compound as the left operand and Simple as
the right operand. It identifies each method using its explanatory definition
(`Interest is charged ...`), requires one `Total Interest` row on that page, and
requires dollar-denominated furniture-example context.

Selected facts:

- Compound Interest, page 50: Total Interest = $521; and
- Simple Interest, page 49: Total Interest = $440.

## Reliability result

The ordered calculation is `521 - 440 = 81`, direction `more`.

- `$81 more`: accepted;
- `$81 less`: rejected for comparative polarity mismatch.

## Post-prediction score

After freezing the prediction, the development benchmark was opened:

- benchmark answer: `$81`;
- normalized currency match: pass; and
- selected pages 49 and 50 versus benchmark pages 49 and 50: complete match.

This selector covers the observed method-scoped Total Interest structure; it is not
a general financial-table parser. Paid API cost: `$0`.
