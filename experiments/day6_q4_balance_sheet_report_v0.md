# Day 6 compared balance-sheet Total Assets v0

## Question

How much larger are the credit-card subsidiary's Total Assets than the credit
company's Total Assets at June 30, 2007, in billion yen?

## Label-free selection

Hybrid RRF Top 10 places the two relevant pages first and second. The question does
not identify the companies by name; it distinguishes them by balance-sheet rows.
The selector therefore links:

- `Installment accounts receivable` to the Rakuten KC balance sheet on page 62,
  Total Assets 336.3 billion yen; and
- the standalone `Loan receivables` current-asset row to the Rakuten Credit balance
  sheet on page 66, Total Assets 82.7 billion yen.

Both pages must contain a Balance Sheet title, the June 30, 2007 date, one Total
Assets value, and the Billion Yen unit. A test ensures that `securitized loan
receivables` is not mistaken for the standalone target row.

## Reliability result

The ordered calculation is `336.3 - 82.7 = 253.6`, direction `larger`.

- `253.6 billion yen larger`: accepted;
- `253.6 billion yen less`: rejected for comparative polarity mismatch.

The first audit naively pluralized the multiword unit as `billion yens`. That v0 is
retained as provenance. The shared-unit formatter was corrected and tested; v1
preserves `billion yen`.

## Post-prediction score

After freezing the prediction, the development benchmark was opened:

- benchmark answer: 253.6;
- normalized value and requested-unit match: pass; and
- selected pages 62 and 66 versus benchmark pages 62 and 66: complete match.

This is an entity-discriminated Total Assets selector, not a general balance-sheet
parser. Paid API cost: `$0`.
