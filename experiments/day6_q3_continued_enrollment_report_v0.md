# Day 6 continued enrolment table comparison v0

## Question

How many more part-time female students are enrolled in Bachelor's and first
professional degree programs compared with part-time male students in Fall 2008?

## Observed failure class

The value pages repeat the table header and contain the Grand Total rows, but omit
the Male/Female table titles. Those titles appear on the immediately preceding
pages. Reading pages 5 and 7 alone therefore preserves the values but loses group
identity.

## Label-free selection

Hybrid RRF Top 10 already contains pages 4, 5, 6, and 7. The deterministic selector:

1. parses Female as the left operand and Male as the right operand from the question;
2. locates the Male table title and header on page 4;
3. validates page 5 as its continuation using the repeated six-column header;
4. locates the Female table title and header on page 6;
5. validates page 7 as its continuation; and
6. reads the Bachelor's Part-Time value from the second Grand Total column.

Selected facts:

- Female, page 7: 1,503 students; and
- Male, page 5: 564 students.

Supporting scope pages 6 and 4 supply the gender identities. They are retained as
provenance but are not presented as the pages containing the final numeric values.

## Reliability result

The deterministic comparison is `1503 - 564 = 939`, direction `more`.
A candidate stating `939 more` is accepted. A candidate stating `939 fewer` is
rejected for comparative polarity mismatch even though its magnitude is correct.

## Post-prediction score

After freezing the prediction, the development benchmark was opened:

- benchmark answer: 939;
- exact answer match: pass; and
- selected value pages 5 and 7 versus benchmark pages 5 and 7: complete match.

This is a narrow continuation-aware enrolment-table selector, not a general PDF
table parser. Paid API cost: `$0`.
